#include <Arduino.h>
#include <Audio.h>
#include <Wire.h>
#include <SPI.h>

#include "dsp.h"

// ===================== PARAMS / PROFILES =====================
struct UserProfile {
  float gainGlobal;
  float g500;
  float g2000;
  float g4000;
};

UserProfile ALICE = {1.0f,  6.0f, 12.0f, 18.0f};
UserProfile BOB   = {1.0f,  0.0f,  8.0f, 10.0f};

static void printStatus() {
  DspParams p = dspGet();
  Serial.println("STATUS");
  Serial.print("GAIN ");   Serial.println(p.gainGlobal, 3);
  Serial.print("EQ500 ");  Serial.println(p.g500, 2);
  Serial.print("EQ2000 "); Serial.println(p.g2000, 2);
  Serial.print("EQ4000 "); Serial.println(p.g4000, 2);
  Serial.println("END");
}

static void parseCommand(const String& lineRaw) {
  String line = lineRaw;
  line.trim();
  if (line.length() == 0) return;

  int sp = line.indexOf(' ');
  String cmd = (sp == -1) ? line : line.substring(0, sp);
  String arg = (sp == -1) ? ""   : line.substring(sp + 1);
  cmd.toUpperCase();
  arg.trim();

  DspParams p = dspGet();

  if (cmd == "GAIN") {
    p.gainGlobal = arg.toFloat();
    dspApply(p);
    Serial.println("OK");
    return;
  }

  if (cmd == "EQ500") {
    p.g500 = arg.toFloat();
    dspApply(p);
    Serial.println("OK");
    return;
  }

  if (cmd == "EQ2000") {
    p.g2000 = arg.toFloat();
    dspApply(p);
    Serial.println("OK");
    return;
  }

  if (cmd == "EQ4000") {
    p.g4000 = arg.toFloat();
    dspApply(p);
    Serial.println("OK");
    return;
  }

  if (cmd == "PROFILE") {
    String name = arg; name.toUpperCase();
    if (name == "ALICE") {
      dspApply({ALICE.gainGlobal, ALICE.g500, ALICE.g2000, ALICE.g4000});
      Serial.println("OK");
      return;
    }
    if (name == "BOB") {
      dspApply({BOB.gainGlobal, BOB.g500, BOB.g2000, BOB.g4000});
      Serial.println("OK");
      return;
    }
    Serial.println("ERR Unknown profile");
    return;
  }

  if (cmd == "STATUS") {
    printStatus();
    return;
  }

  Serial.println("ERR Unknown command");
}

void setup() {
  AudioMemory(40);
  Serial.begin(115200);
  delay(200);

  dspInit();

  Serial.println("READY");
}

void loop() {
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    parseCommand(line);
  }
}
