import tkinter as tk
from tkinter import ttk, messagebox
import time, threading, random, json, os
import serial
from serial.tools import list_ports

# =========================
# Config audiogram (8 freqs)
# =========================
FREQS = [250, 500, 1000, 2000, 3000, 4000, 6000, 8000]

TONE_DUR = 0.45
GAP_DUR  = 0.25
PAUSE_BETWEEN_TRIALS = 0.25

START_DB = -45.0
MIN_DB   = -80.0
MAX_DB   = -3.0

STEP_LARGE = 6.0
STEP_MED   = 3.0
STEP_SMALL = 2.0

STOP_REVERSALS = 6
AVG_LAST_REVERSALS = 4

# Map thresholds -> 3 EQ bands
BAND_EQ500  = [250, 500]
BAND_EQ2000 = [1000, 2000, 3000]
BAND_EQ4000 = [4000, 6000, 8000]

GAIN_FACTOR = 0.5
GAIN_MAX_DB = 25.0
GAIN_MIN_DB = 0.0

PROFILES_DIR = "profiles"


# =========================
# Serial helpers
# =========================
class TeensyLink:
    def __init__(self):
        self.ser = None

    def connect(self, port, baud=115200):
        self.ser = serial.Serial(port, baud, timeout=0.2)
        time.sleep(0.25)

    def close(self):
        if self.ser:
            try:
                self.ser.close()
            except:
                pass
        self.ser = None

    def send(self, cmd: str):
        if not self.ser:
            raise RuntimeError("Not connected to Teensy")
        self.ser.write((cmd.strip() + "\n").encode("utf-8"))

    def set_test_mode(self, on: bool):
        self.send("TEST ON" if on else "TEST OFF")

    def set_freq(self, hz: float):
        self.send(f"FREQ {hz}")

    def set_level_db(self, db: float):
        self.send(f"LEVEL {db:.1f}")

    def apply_eq(self, g500, g2000, g4000, gain_global=1.0):
        # Apply in this order
        self.send(f"GAIN {gain_global:.3f}")
        self.send(f"EQ500 {g500:.1f}")
        self.send(f"EQ2000 {g2000:.1f}")
        self.send(f"EQ4000 {g4000:.1f}")


# =========================
# 2AFC staircase
# =========================
class Staircase2Down1Up:
    def __init__(self, start_db=START_DB):
        self.level_db = start_db
        self.step = STEP_LARGE
        self.reversals = []
        self.last_dir = None
        self.correct_streak = 0

    def clamp(self):
        self.level_db = max(MIN_DB, min(MAX_DB, self.level_db))

    def maybe_update_step(self):
        if len(self.reversals) >= 2:
            self.step = STEP_SMALL
        elif len(self.reversals) >= 1:
            self.step = STEP_MED
        else:
            self.step = STEP_LARGE

    def update(self, correct: bool):
        if correct:
            self.correct_streak += 1
            if self.correct_streak >= 2:
                self.correct_streak = 0
                new_dir = "down"
                self.level_db -= self.step
            else:
                new_dir = self.last_dir
        else:
            self.correct_streak = 0
            new_dir = "up"
            self.level_db += self.step

        if self.last_dir is not None and new_dir is not None and new_dir != self.last_dir:
            self.reversals.append(self.level_db)

        self.last_dir = new_dir
        self.maybe_update_step()
        self.clamp()

    def done(self):
        return len(self.reversals) >= STOP_REVERSALS

    def threshold(self):
        if not self.reversals:
            return self.level_db
        tail = self.reversals[-AVG_LAST_REVERSALS:] if len(self.reversals) >= AVG_LAST_REVERSALS else self.reversals
        return sum(tail) / len(tail)


# =========================
# Audiogram -> EQ
# =========================
def compute_eq_from_thresholds(thresholds):
    ref = min(thresholds.values())
    losses = {f: (thresholds[f] - ref) for f in thresholds}

    def band_gain(freq_list):
        vals = [losses[f] for f in freq_list if f in losses]
        if not vals:
            return 0.0
        loss = sum(vals) / len(vals)
        gain = GAIN_FACTOR * loss
        gain = max(GAIN_MIN_DB, min(GAIN_MAX_DB, gain))
        return gain

    g500  = band_gain(BAND_EQ500)
    g2000 = band_gain(BAND_EQ2000)
    g4000 = band_gain(BAND_EQ4000)

    details = {
        "reference_db": float(ref),
        "losses_db": {str(k): float(v) for k, v in losses.items()},
        "band_map": {"EQ500": BAND_EQ500, "EQ2000": BAND_EQ2000, "EQ4000": BAND_EQ4000},
        "rule": f"gain = {GAIN_FACTOR} * loss (clipped {GAIN_MIN_DB}..{GAIN_MAX_DB} dB)"
    }
    return g500, g2000, g4000, details


# =========================
# Profile storage (JSON)
# =========================
def ensure_profiles_dir():
    os.makedirs(PROFILES_DIR, exist_ok=True)

def safe_name(name: str) -> str:
    # keep it simple for filenames
    name = name.strip()
    name = "".join(c for c in name if c.isalnum() or c in ("-", "_", " "))
    name = name.strip().replace(" ", "_")
    return name

def profile_path(name: str) -> str:
    ensure_profiles_dir()
    return os.path.join(PROFILES_DIR, f"{safe_name(name)}.json")

def list_profiles():
    ensure_profiles_dir()
    out = []
    for fn in os.listdir(PROFILES_DIR):
        if fn.lower().endswith(".json"):
            out.append(os.path.splitext(fn)[0].replace("_", " "))
    out.sort(key=lambda s: s.lower())
    return out

def save_profile(name: str, data: dict):
    p = profile_path(name)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def load_profile(name: str) -> dict:
    p = profile_path(name)
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

def delete_profile(name: str):
    p = profile_path(name)
    if os.path.exists(p):
        os.remove(p)


# =========================
# GUI
# =========================
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Hearing Aid – 2AFC Audiogram + Profiles")

        self.link = TeensyLink()

        # audiogram state
        self.worker = None
        self.running = False
        self.awaiting_answer = False
        self.correct_interval = 1
        self.current_freq = None
        self.current_sc = None
        self.results = {}  # freq -> threshold_db

        # current EQ settings (GUI sliders)
        self.gain_global = tk.DoubleVar(value=1.0)
        self.eq500 = tk.DoubleVar(value=0.0)
        self.eq2000 = tk.DoubleVar(value=0.0)
        self.eq4000 = tk.DoubleVar(value=0.0)

        # profile selection
        self.profile_var = tk.StringVar(value="")
        self.profile_name_var = tk.StringVar(value="")

        self._build_ui()
        self._refresh_ports()
        self._refresh_profiles()

        # Key bindings for fast 2AFC
        self.root.bind("<a>", lambda e: self.answer(1))
        self.root.bind("<A>", lambda e: self.answer(1))
        self.root.bind("<b>", lambda e: self.answer(2))
        self.root.bind("<B>", lambda e: self.answer(2))

    def _build_ui(self):
        frm = ttk.Frame(self.root, padding=10)
        frm.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        # ==== Connection row
        ttk.Label(frm, text="Teensy serial port:").grid(row=0, column=0, sticky="w")
        self.port_var = tk.StringVar()
        self.port_combo = ttk.Combobox(frm, textvariable=self.port_var, state="readonly", width=30)
        self.port_combo.grid(row=0, column=1, sticky="w", padx=(6, 6))
        ttk.Button(frm, text="Refresh", command=self._refresh_ports).grid(row=0, column=2, sticky="w")

        self.conn_btn = ttk.Button(frm, text="Connect", command=self.toggle_connect)
        self.conn_btn.grid(row=1, column=0, sticky="w", pady=(6, 0))

        self.status_var = tk.StringVar(value="Not connected.")
        ttk.Label(frm, textvariable=self.status_var).grid(row=1, column=1, columnspan=2, sticky="w", pady=(6, 0))

        ttk.Separator(frm).grid(row=2, column=0, columnspan=3, sticky="ew", pady=10)

        # ==== Manual EQ control (sliders) + apply
        ttk.Label(frm, text="Manual fitting (sliders):").grid(row=3, column=0, sticky="w")

        sfrm = ttk.Frame(frm)
        sfrm.grid(row=4, column=0, columnspan=3, sticky="ew")
        sfrm.columnconfigure(1, weight=1)

        ttk.Label(sfrm, text="Gain global (x)").grid(row=0, column=0, sticky="w")
        ttk.Scale(sfrm, from_=0.2, to=3.0, orient="horizontal",
                  variable=self.gain_global).grid(row=0, column=1, sticky="ew", padx=6)
        self.lbl_gain = ttk.Label(sfrm, text="1.00")
        self.lbl_gain.grid(row=0, column=2, sticky="w")

        ttk.Label(sfrm, text="EQ 500 Hz (dB)").grid(row=1, column=0, sticky="w")
        ttk.Scale(sfrm, from_=-20, to=30, orient="horizontal",
                  variable=self.eq500).grid(row=1, column=1, sticky="ew", padx=6)
        self.lbl_500 = ttk.Label(sfrm, text="0.0")
        self.lbl_500.grid(row=1, column=2, sticky="w")

        ttk.Label(sfrm, text="EQ 2 kHz (dB)").grid(row=2, column=0, sticky="w")
        ttk.Scale(sfrm, from_=-20, to=30, orient="horizontal",
                  variable=self.eq2000).grid(row=2, column=1, sticky="ew", padx=6)
        self.lbl_2000 = ttk.Label(sfrm, text="0.0")
        self.lbl_2000.grid(row=2, column=2, sticky="w")

        ttk.Label(sfrm, text="EQ 4 kHz (dB)").grid(row=3, column=0, sticky="w")
        ttk.Scale(sfrm, from_=-20, to=30, orient="horizontal",
                  variable=self.eq4000).grid(row=3, column=1, sticky="ew", padx=6)
        self.lbl_4000 = ttk.Label(sfrm, text="0.0")
        self.lbl_4000.grid(row=3, column=2, sticky="w")

        btnrow = ttk.Frame(frm)
        btnrow.grid(row=5, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Button(btnrow, text="Apply sliders to Teensy", command=self.apply_sliders).grid(row=0, column=0, padx=(0, 8))

        self.gain_global.trace_add("write", lambda *_: self._update_slider_labels())
        self.eq500.trace_add("write", lambda *_: self._update_slider_labels())
        self.eq2000.trace_add("write", lambda *_: self._update_slider_labels())
        self.eq4000.trace_add("write", lambda *_: self._update_slider_labels())
        self._update_slider_labels()

        ttk.Separator(frm).grid(row=6, column=0, columnspan=3, sticky="ew", pady=10)

        # ==== Profiles
        ttk.Label(frm, text="Profiles:").grid(row=7, column=0, sticky="w")

        pfrm = ttk.Frame(frm)
        pfrm.grid(row=8, column=0, columnspan=3, sticky="ew")
        pfrm.columnconfigure(1, weight=1)

        ttk.Label(pfrm, text="Select").grid(row=0, column=0, sticky="w")
        self.profile_combo = ttk.Combobox(pfrm, textvariable=self.profile_var, state="readonly", width=28)
        self.profile_combo.grid(row=0, column=1, sticky="w", padx=6)
        ttk.Button(pfrm, text="Refresh", command=self._refresh_profiles).grid(row=0, column=2, sticky="w")

        ttk.Label(pfrm, text="New/Name").grid(row=1, column=0, sticky="w")
        ttk.Entry(pfrm, textvariable=self.profile_name_var, width=30).grid(row=1, column=1, sticky="w", padx=6)

        profbtns = ttk.Frame(frm)
        profbtns.grid(row=9, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Button(profbtns, text="Load → sliders", command=self.load_selected_into_sliders).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(profbtns, text="Apply selected to Teensy", command=self.apply_selected_profile).grid(row=0, column=1, padx=(0, 8))
        ttk.Button(profbtns, text="Save/Update from sliders", command=self.save_from_sliders).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(profbtns, text="Delete selected", command=self.delete_selected).grid(row=0, column=3)

        ttk.Separator(frm).grid(row=10, column=0, columnspan=3, sticky="ew", pady=10)

        # ==== Audiogram 2AFC
        audfrm = ttk.Frame(frm)
        audfrm.grid(row=11, column=0, columnspan=3, sticky="ew")
        ttk.Label(audfrm, text="Audiogram (2AFC A/B, 8 freqs):").grid(row=0, column=0, sticky="w")

        self.start_btn = ttk.Button(audfrm, text="Start Audiogram", command=self.start_audiogram)
        self.start_btn.grid(row=1, column=0, sticky="w", pady=(6, 0))

        self.stop_btn = ttk.Button(audfrm, text="Stop", command=self.stop_audiogram, state="disabled")
        self.stop_btn.grid(row=1, column=1, sticky="w", pady=(6, 0), padx=(8, 0))

        self.prompt_var = tk.StringVar(value="Keys A/B work during test.")
        ttk.Label(audfrm, textvariable=self.prompt_var, wraplength=620).grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 0))

        ab = ttk.Frame(audfrm)
        ab.grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self.btnA = ttk.Button(ab, text="A", command=lambda: self.answer(1), state="disabled", width=8)
        self.btnB = ttk.Button(ab, text="B", command=lambda: self.answer(2), state="disabled", width=8)
        self.btnA.grid(row=0, column=0, padx=(0, 8))
        self.btnB.grid(row=0, column=1)

        # Results table
        self.tree = ttk.Treeview(frm, columns=("freq", "thr"), show="headings", height=8)
        self.tree.heading("freq", text="Frequency (Hz)")
        self.tree.heading("thr", text="Threshold (dB rel)")
        self.tree.column("freq", width=140, anchor="center")
        self.tree.column("thr", width=160, anchor="center")
        self.tree.grid(row=12, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
        frm.rowconfigure(12, weight=1)

        # Buttons after audiogram
        aft = ttk.Frame(frm)
        aft.grid(row=13, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self.compute_btn = ttk.Button(aft, text="Compute EQ → sliders", command=self.compute_eq_to_sliders, state="disabled")
        self.compute_btn.grid(row=0, column=0, padx=(0, 8))
        self.save_auto_btn = ttk.Button(aft, text="Save as profile name →", command=self.save_audiogram_as_profile, state="disabled")
        self.save_auto_btn.grid(row=0, column=1, padx=(0, 8))
        self.apply_auto_btn = ttk.Button(aft, text="Apply computed EQ to Teensy", command=self.apply_computed_eq, state="disabled")
        self.apply_auto_btn.grid(row=0, column=2)

        self.eq_info_var = tk.StringVar(value="Computed EQ: (none)")
        ttk.Label(frm, textvariable=self.eq_info_var).grid(row=14, column=0, columnspan=3, sticky="w", pady=(6, 0))

    # ---------- Ports / connect ----------
    def _refresh_ports(self):
        ports = [p.device for p in list_ports.comports()]
        self.port_combo["values"] = ports
        if ports and not self.port_var.get():
            self.port_var.set(ports[0])

    def toggle_connect(self):
        if self.link.ser:
            self.link.close()
            self.conn_btn.config(text="Connect")
            self.status_var.set("Not connected.")
            return

        port = self.port_var.get().strip()
        if not port:
            messagebox.showerror("Port", "Select a serial port.")
            return
        try:
            self.link.connect(port)
            self.conn_btn.config(text="Disconnect")
            self.status_var.set(f"Connected: {port}")
        except Exception as e:
            messagebox.showerror("Connect failed", str(e))

    # ---------- Slider apply ----------
    def _update_slider_labels(self):
        self.lbl_gain.config(text=f"{self.gain_global.get():.2f}")
        self.lbl_500.config(text=f"{self.eq500.get():.1f}")
        self.lbl_2000.config(text=f"{self.eq2000.get():.1f}")
        self.lbl_4000.config(text=f"{self.eq4000.get():.1f}")

    def apply_sliders(self):
        if not self.link.ser:
            messagebox.showerror("Not connected", "Connect to Teensy first.")
            return
        try:
            self.link.apply_eq(
                self.eq500.get(),
                self.eq2000.get(),
                self.eq4000.get(),
                gain_global=self.gain_global.get()
            )
            messagebox.showinfo("Applied", "Sliders applied to Teensy.")
        except Exception as e:
            messagebox.showerror("Apply failed", str(e))

    # ---------- Profiles ----------
    def _refresh_profiles(self):
        profs = list_profiles()
        self.profile_combo["values"] = profs
        # keep selection if still exists
        cur = self.profile_var.get().strip()
        if cur and cur in profs:
            return
        if profs:
            self.profile_var.set(profs[0])
        else:
            self.profile_var.set("")

    def _selected_profile_name(self):
        return self.profile_var.get().strip()

    def load_selected_into_sliders(self):
        name = self._selected_profile_name()
        if not name:
            messagebox.showerror("Profile", "No profile selected.")
            return
        try:
            data = load_profile(name)
            eq = data.get("eq", {})
            self.gain_global.set(float(eq.get("GAIN_global", 1.0)))
            self.eq500.set(float(eq.get("EQ500_db", 0.0)))
            self.eq2000.set(float(eq.get("EQ2000_db", 0.0)))
            self.eq4000.set(float(eq.get("EQ4000_db", 0.0)))
            self.profile_name_var.set(name)
            self.eq_info_var.set(f"Loaded profile '{name}'.")
        except Exception as e:
            messagebox.showerror("Load failed", str(e))

    def apply_selected_profile(self):
        if not self.link.ser:
            messagebox.showerror("Not connected", "Connect to Teensy first.")
            return
        name = self._selected_profile_name()
        if not name:
            messagebox.showerror("Profile", "No profile selected.")
            return
        try:
            data = load_profile(name)
            eq = data.get("eq", {})
            gg = float(eq.get("GAIN_global", 1.0))
            g500 = float(eq.get("EQ500_db", 0.0))
            g2000 = float(eq.get("EQ2000_db", 0.0))
            g4000 = float(eq.get("EQ4000_db", 0.0))
            self.link.apply_eq(g500, g2000, g4000, gain_global=gg)
            messagebox.showinfo("Applied", f"Profile '{name}' applied to Teensy.")
        except Exception as e:
            messagebox.showerror("Apply failed", str(e))

    def save_from_sliders(self):
        name = self.profile_name_var.get().strip()
        if not name:
            messagebox.showerror("Profile name", "Enter a profile name (New/Name).")
            return

        data = {
            "method": "manual sliders",
            "thresholds_db_rel": None,
            "eq": {
                "GAIN_global": float(self.gain_global.get()),
                "EQ500_db": float(self.eq500.get()),
                "EQ2000_db": float(self.eq2000.get()),
                "EQ4000_db": float(self.eq4000.get()),
            },
            "notes": {}
        }
        try:
            save_profile(name, data)
            self._refresh_profiles()
            # set selection to this profile
            # (stored filename uses underscores, so we use display name)
            display = name.strip()
            self.profile_var.set(display)
            messagebox.showinfo("Saved", f"Profile saved/updated: {display}")
        except Exception as e:
            messagebox.showerror("Save failed", str(e))

    def delete_selected(self):
        name = self._selected_profile_name()
        if not name:
            messagebox.showerror("Profile", "No profile selected.")
            return
        if messagebox.askyesno("Delete", f"Delete profile '{name}' ?"):
            try:
                delete_profile(name)
                self._refresh_profiles()
            except Exception as e:
                messagebox.showerror("Delete failed", str(e))

    # ---------- Audiogram ----------
    def start_audiogram(self):
        if not self.link.ser:
            messagebox.showerror("Not connected", "Connect to Teensy first.")
            return
        if self.running:
            return

        self.results = {}
        self._refresh_table()

        self.running = True
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.compute_btn.config(state="disabled")
        self.save_auto_btn.config(state="disabled")
        self.apply_auto_btn.config(state="disabled")
        self.eq_info_var.set("Computed EQ: (none)")

        self.prompt_var.set("Entering TEST mode…")
        try:
            self.link.set_test_mode(True)
        except Exception as e:
            messagebox.showerror("Serial", str(e))
            self.stop_audiogram()
            return

        self.worker = threading.Thread(target=self._worker_run, daemon=True)
        self.worker.start()

    def stop_audiogram(self):
        self.running = False
        self.awaiting_answer = False
        self.btnA.config(state="disabled")
        self.btnB.config(state="disabled")

        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")

        if self.link.ser:
            try:
                self.link.set_test_mode(False)
            except:
                pass

        self.prompt_var.set("Stopped. You can start again.")

    def _worker_run(self):
        try:
            for idx, f in enumerate(FREQS, start=1):
                if not self.running:
                    break

                self.current_freq = f
                self.current_sc = Staircase2Down1Up(start_db=START_DB)

                self._ui(lambda: self.prompt_var.set(f"[{idx}/{len(FREQS)}] {f} Hz — answer A/B (keyboard works)."))
                self.link.set_freq(f)
                time.sleep(0.15)

                while self.running and not self.current_sc.done():
                    self.correct_interval = 1 if random.random() < 0.5 else 2
                    level_db = self.current_sc.level_db

                    self._ui(lambda lvl=level_db: self.prompt_var.set(
                        f"{f} Hz | level {lvl:.1f} dB | Where was the tone? A or B"
                    ))

                    self._play_interval(1, level_db if self.correct_interval == 1 else -90.0)
                    time.sleep(GAP_DUR)
                    self._play_interval(2, level_db if self.correct_interval == 2 else -90.0)

                    self.awaiting_answer = True
                    self._ui(lambda: (self.btnA.config(state="normal"), self.btnB.config(state="normal")))
                    while self.running and self.awaiting_answer:
                        time.sleep(0.02)
                    self._ui(lambda: (self.btnA.config(state="disabled"), self.btnB.config(state="disabled")))

                    time.sleep(PAUSE_BETWEEN_TRIALS)

                if not self.running:
                    break

                thr = self.current_sc.threshold()
                self.results[f] = thr
                self._ui(self._refresh_table)

            # done
            try:
                self.link.set_test_mode(False)
            except:
                pass

            if self.running:
                self._ui(lambda: self.prompt_var.set("Audiogram complete ✅"))
                self._ui(lambda: self.compute_btn.config(state="normal"))
                self._ui(lambda: self.save_auto_btn.config(state="normal"))
                self._ui(lambda: self.apply_auto_btn.config(state="normal"))

        except Exception as e:
            self._ui(lambda: messagebox.showerror("Error", str(e)))
        finally:
            self._ui(lambda: self.start_btn.config(state="normal"))
            self._ui(lambda: self.stop_btn.config(state="disabled"))
            self.running = False

    def _play_interval(self, interval_num: int, db_level: float):
        self._ui(lambda n=interval_num: self.prompt_var.set(f"Playing interval {'A' if n==1 else 'B'}…"))
        self.link.set_level_db(db_level)
        time.sleep(TONE_DUR)
        self.link.set_level_db(-90.0)
        time.sleep(0.05)

    def answer(self, choice_interval: int):
        if not (self.running and self.awaiting_answer and self.current_sc):
            return
        correct = (choice_interval == self.correct_interval)
        self.current_sc.update(correct)
        self.awaiting_answer = False

    def _refresh_table(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        for f in FREQS:
            self.tree.insert("", "end", values=(f, f"{self.results.get(f, '—') if f in self.results else '—'}"))

    # ---------- After audiogram actions ----------
    def compute_eq_to_sliders(self):
        if not self.results:
            messagebox.showerror("No data", "Run audiogram first.")
            return
        g500, g2000, g4000, details = compute_eq_from_thresholds(self.results)
        self.eq500.set(g500)
        self.eq2000.set(g2000)
        self.eq4000.set(g4000)
        self.eq_info_var.set(f"Computed EQ: EQ500={g500:.1f} | EQ2000={g2000:.1f} | EQ4000={g4000:.1f}")

    def apply_computed_eq(self):
        if not self.link.ser:
            messagebox.showerror("Not connected", "Connect to Teensy first.")
            return
        if not self.results:
            messagebox.showerror("No data", "Run audiogram first.")
            return
        g500, g2000, g4000, details = compute_eq_from_thresholds(self.results)
        try:
            self.link.apply_eq(g500, g2000, g4000, gain_global=self.gain_global.get())
            messagebox.showinfo("Applied", "Computed EQ applied to Teensy.")
        except Exception as e:
            messagebox.showerror("Apply failed", str(e))

    def save_audiogram_as_profile(self):
        if not self.results:
            messagebox.showerror("No data", "Run audiogram first.")
            return
        name = self.profile_name_var.get().strip()
        if not name:
            messagebox.showerror("Profile name", "Enter a profile name (New/Name) before saving.")
            return

        g500, g2000, g4000, details = compute_eq_from_thresholds(self.results)
        data = {
            "method": "2AFC 2-down-1-up (relative)",
            "freqs_hz": FREQS,
            "thresholds_db_rel": {str(k): float(v) for k, v in self.results.items()},
            "eq": {
                "GAIN_global": float(self.gain_global.get()),
                "EQ500_db": float(g500),
                "EQ2000_db": float(g2000),
                "EQ4000_db": float(g4000),
            },
            "notes": details,
        }
        try:
            save_profile(name, data)
            self._refresh_profiles()
            self.profile_var.set(name)
            messagebox.showinfo("Saved", f"Audiogram profile saved: {name}")
        except Exception as e:
            messagebox.showerror("Save failed", str(e))

    def _ui(self, fn):
        self.root.after(0, fn)


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
