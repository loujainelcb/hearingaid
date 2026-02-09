#pragma once
#include <Arduino.h>
#include <Audio.h>

// =====================
// DSP: public API
// =====================

struct DspParams {
  float gainGlobal; // multiplicateur (1.0 = 0 dB)
  float g500;       // dB
  float g2000;      // dB
  float g4000;      // dB
};

void dspInit();                       // init audio objects + default params
void dspApply(const DspParams& p);    // apply params (gain + EQ)
DspParams dspGet();                   // read back current params

// Optional: helpers
float clampf(float x, float lo, float hi);
