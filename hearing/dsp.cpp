#include "dsp.h"
#include <math.h>

// Objects
AudioInputUSB        usb_in;
AudioAmplifier       amp;
AudioFilterBiquad    eq1, eq2, eq3;
AudioOutputI2S       i2s_out;
AudioMixer4          inMix;

AudioConnection c0(usb_in, 0, inMix, 0);   // Left -> mix
AudioConnection c0b(usb_in, 1, inMix, 1);  // Right -> mix
AudioConnection c1(inMix, 0, amp, 0);      // mix -> amp
AudioConnection c2(amp, 0, eq1, 0);
AudioConnection c3(eq1, 0, eq2, 0);
AudioConnection c4(eq2, 0, eq3, 0);
AudioConnection c5(eq3, 0, i2s_out, 0);
AudioConnection c6(eq3, 0, i2s_out, 1);


AudioControlSGTL5000 sgtl5000;

// Internal state
static DspParams gParams = {1.0f, 0.0f, 0.0f, 0.0f};
static const float Q_500  = 1.0f;
static const float Q_2000 = 1.0f;
static const float Q_4000 = 1.0f;

float clampf(float x, float lo, float hi) {
  if (x < lo) return lo;
  if (x > hi) return hi;
  return x;
}

static void biquadPeaking(AudioFilterBiquad& f, int stage,
                          float freqHz, float Q, float gainDB) {
  const float Fs = AUDIO_SAMPLE_RATE_EXACT;

  float A = powf(10.0f, gainDB / 40.0f);
  float w0 = 2.0f * (float)M_PI * freqHz / Fs;
  float alpha = sinf(w0) / (2.0f * Q);
  float cosw0 = cosf(w0);

  float b0 = 1.0f + alpha * A;
  float b1 = -2.0f * cosw0;
  float b2 = 1.0f - alpha * A;
  float a0 = 1.0f + alpha / A;
  float a1 = -2.0f * cosw0;
  float a2 = 1.0f - alpha / A;

  b0 /= a0; b1 /= a0; b2 /= a0;
  a1 /= a0; a2 /= a0;

  double c[5] = { b0, b1, b2, a1, a2 };
  f.setCoefficients((uint32_t)stage, c);
}

static void applyInternal() {
  amp.gain(gParams.gainGlobal);
  biquadPeaking(eq1, 0,  500.0f, Q_500,  gParams.g500);
  biquadPeaking(eq2, 0, 2000.0f, Q_2000, gParams.g2000);
  biquadPeaking(eq3, 0, 4000.0f, Q_4000, gParams.g4000);
}

void dspInit() {
  sgtl5000.enable();
  sgtl5000.volume(0.5f);

  inMix.gain(0, 0.5f);   // Left
  inMix.gain(1, 0.5f);   // Right
  inMix.gain(2, 0.0f);
  inMix.gain(3, 0.0f);

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
