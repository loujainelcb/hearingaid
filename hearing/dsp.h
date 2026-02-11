#pragma once
#include <Arduino.h>
#include <Audio.h>


struct DspParams {
  float gainGlobal;
  float g500;
  float g2000;
  float g4000;
};

void dspInit();
void dspApply(const DspParams& p);
DspParams dspGet();

// --- Audiogram TEST mode API (needed by gui.py) ---
void dspSetTestMode(bool on);
void dspSetTestFreq(float hz);
void dspSetTestLevelDb(float db);

// helpers
float clampf(float x, float lo, float hi);
