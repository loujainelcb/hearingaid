#include "dsp.h"
#include <math.h>

// ===== Audio Shield path =====
AudioInputUSB        usb_in;

AudioAmplifier       amp;
AudioFilterBiquad    eq1, eq2, eq3;

AudioSynthWaveform   testTone;
AudioMixer4          outMix;        // 0=normal audio, 1=test tone

AudioOutputI2S       i2s_out;
AudioControlSGTL5000 sgtl5000;

AudioInputI2S mic_in;
AudioMixer4 inMix;   // mixer des entrées (USB / micro)

// normal: USB in -> amp -> eq1 -> eq2 -> eq3 -> mix ch0
// ===== Audio connections =====

// USB + Micro -> inMix
AudioConnection pc_usb_to_mix(usb_in, 0, inMix, 0);
AudioConnection mic_to_mix(mic_in, 0, inMix, 1);

// inMix -> amp -> EQ -> outMix
AudioConnection mix_to_amp(inMix, 0, amp, 0);
AudioConnection amp_to_eq1(amp, 0, eq1, 0);
AudioConnection eq1_to_eq2(eq1, 0, eq2, 0);
AudioConnection eq2_to_eq3(eq2, 0, eq3, 0);
AudioConnection eq3_to_out(eq3, 0, outMix, 0);

// test tone -> outMix ch1
AudioConnection test_to_out(testTone, 0, outMix, 1);

// outMix -> Audio Shield L / R
AudioConnection out_to_L(outMix, 0, i2s_out, 0);
AudioConnection out_to_R(outMix, 0, i2s_out, 1);


// ===== state =====
static DspParams gParams = {1.0f, 0.0f, 0.0f, 0.0f};
static bool  gTestMode = false;
static float gTestFreq = 1000.0f;
static float gTestDb   = -90.0f;

static const float Q_500  = 1.0f;
static const float Q_2000 = 1.0f;
static const float Q_4000 = 1.0f;

float clampf(float x, float lo, float hi) {
  if (x < lo) return lo;
  if (x > hi) return hi;
  return x;
}

static float dbToAmp(float db) {
  if (db <= -90.0f) return 0.0f;
  float a = powf(10.0f, db / 20.0f);
  return clampf(a, 0.0f, 1.0f);
}

// --- biquadPeaking(...) : garde ta version qui marche chez toi (setCoefficients avec double[5]) ---
static void biquadPeaking(AudioFilterBiquad& f, int stage, float freqHz, float Q, float gainDB) {
  // RBJ Audio EQ Cookbook - Peaking EQ
  const double Fs = AUDIO_SAMPLE_RATE_EXACT;

  const double A = pow(10.0, (double)gainDB / 40.0);
  const double w0 = 2.0 * M_PI * (double)freqHz / Fs;
  const double alpha = sin(w0) / (2.0 * (double)Q);
  const double cosw0 = cos(w0);

  double b0 = 1.0 + alpha * A;
  double b1 = -2.0 * cosw0;
  double b2 = 1.0 - alpha * A;
  double a0 = 1.0 + alpha / A;
  double a1 = -2.0 * cosw0;
  double a2 = 1.0 - alpha / A;

  // normalize (a0 -> 1)
  b0 /= a0; b1 /= a0; b2 /= a0;
  a1 /= a0; a2 /= a0;

  // Teensy Audio biquad expects {b0, b1, b2, a1, a2}
  double c[5] = { b0, b1, b2, a1, a2 };
  f.setCoefficients((uint32_t)stage, c);
}

static void applyInternal() {
  amp.gain(gParams.gainGlobal);

  biquadPeaking(eq1, 0,  500.0f, Q_500,  gParams.g500);
  biquadPeaking(eq2, 0, 2000.0f, Q_2000, gParams.g2000);
  biquadPeaking(eq3, 0, 4000.0f, Q_4000, gParams.g4000);

  // routing
  outMix.gain(0, gTestMode ? 0.0f : 1.0f);  // normal
  outMix.gain(1, gTestMode ? 1.0f : 0.0f);  // test tone

  testTone.frequency(gTestFreq);
  testTone.amplitude(dbToAmp(gTestDb));
}

void dspInit() {
  // Audio Shield init
  sgtl5000.enable();
  sgtl5000.volume(0.6);
  // activer micro Audio Shield
  sgtl5000.inputSelect(AUDIO_INPUT_MIC);
  sgtl5000.micGain(40);   // ajuste plus tard (0–63)
   // ajuste si besoin
  testTone.begin(WAVEFORM_SINE);

  gParams = {1.0f, 0.0f, 0.0f, 0.0f};
  gTestMode = false;
  gTestFreq = 1000.0f;
  gTestDb   = -90.0f;
  inMix.gain(0, 1.0f);  // USB
  inMix.gain(1, 0.3f);  // micro (évite larsen)


  

  applyInternal();
}

void dspApply(const DspParams& p) {
  gParams.gainGlobal = clampf(p.gainGlobal, 0.0f, 4.0f);
  gParams.g500  = clampf(p.g500,  -20.0f, 30.0f);
  gParams.g2000 = clampf(p.g2000, -20.0f, 30.0f);
  gParams.g4000 = clampf(p.g4000, -20.0f, 30.0f);
  applyInternal();
}

DspParams dspGet() { return gParams; }

void dspSetTestMode(bool on) { gTestMode = on; applyInternal(); }
void dspSetTestFreq(float hz) { gTestFreq = clampf(hz, 50.0f, 12000.0f); applyInternal(); }
void dspSetTestLevelDb(float db) { gTestDb = clampf(db, -90.0f, -3.0f); applyInternal(); }
