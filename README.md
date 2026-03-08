Hearing Aid System – Audiogram and Digital Signal Processing

Author: Loujaine Lechehab
Engineering Student – Telecommunications & Computer Engineering
INSA Lyon

---

PROJECT DESCRIPTION

This project implements a simplified digital hearing aid system combining:

* Hearing threshold measurement (audiogram)
* Digital signal processing
* Audio equalization
* A graphical interface for testing and configuration

The system measures the user's hearing profile and automatically adjusts audio frequencies to compensate for hearing loss.

---

SYSTEM ARCHITECTURE

The project is composed of three main parts:

1. Python GUI application
2. Teensy DSP audio processing
3. Profile storage and management

The Python application controls the hardware through a serial connection and manages the audiogram testing procedure.

The Teensy board performs real-time audio processing and equalization.

---

FILES STRUCTURE

hearingaid/

gui.py
Graphical interface written in Python using Tkinter.
Controls the audiogram test and communicates with the Teensy board.

dsp.cpp
Digital signal processing implementation for the Teensy board.
Handles equalization filters and audio routing.

dsp.h
Header file defining DSP parameters and control functions.

profiles/
Folder containing saved hearing profiles in JSON format.

---

FEATURES

Audiogram measurement
The system measures hearing thresholds at the following frequencies:

250 Hz
500 Hz
1000 Hz
2000 Hz
3000 Hz
4000 Hz
6000 Hz
8000 Hz

The measurement uses a **2AFC staircase method** (Two-Alternative Forced Choice) to estimate hearing thresholds.

The algorithm adapts the sound level based on the user's responses.

---

EQUALIZATION

Based on the audiogram results, the system computes equalization gains for three frequency bands:

EQ500
EQ2000
EQ4000

These gains compensate for the detected hearing loss.

The DSP implementation applies these corrections using **biquad peaking filters**. 

The equalization parameters are defined in the DSP structure:

* global gain
* 500 Hz band gain
* 2000 Hz band gain
* 4000 Hz band gain 

---

GRAPHICAL INTERFACE

The GUI allows the user to:

Connect to the Teensy board via serial port
Run an automated audiogram test
Manually adjust equalization parameters
Save and load hearing profiles
Apply equalization settings to the device

The interface is implemented using **Tkinter**. 

---

TEST MODE

The Teensy DSP includes a dedicated test mode used during audiogram measurement.

In this mode:

* A pure sine tone is generated
* The tone frequency and amplitude are controlled from the GUI
* The user indicates which interval contained the tone

This allows estimation of hearing thresholds.

---

TECHNOLOGIES USED

Python
Tkinter GUI
Serial communication
C++
Teensy Audio Library
Digital Signal Processing (DSP)

---

FUTURE IMPROVEMENTS

Possible extensions include:

Real-time adaptive hearing correction
More frequency bands for finer equalization
Integration with microphones and headphones
Standalone hearing test application
Mobile interface

