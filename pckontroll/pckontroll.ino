#include <PWM.h>

// Requires software PWM library "PWM"

long lastUpdateTime = 0;
long lastSensor;
bool tilt = true;
const int SENSOR_INTERVAL = 500; // ms

const int DEFAULT_VAL = 180;

 void setup() {
  InitTimersSafe();
  pinMode(A0, INPUT_PULLUP);
  SetPinFrequencySafe(3, 25000);
  SetPinFrequencySafe(9, 25000);
  pwmWrite(3, DEFAULT_VAL);
  pwmWrite(9, DEFAULT_VAL);
  Serial.begin(9600);
  lastSensor = millis();
}

void loop() {
  long now = millis();
  if (Serial.available() >= 3) {
    int error = 0;
    while(Serial.read() != 'F') {
      if (error++ == 3) continue;
    }
    int fanSetting = Serial.read();
    int pumpSetting = Serial.read();
    pwmWrite(3, fanSetting);
    pwmWrite(9, pumpSetting);
    tilt = false;
    lastUpdateTime = now;
  }
  if (now - lastUpdateTime > 3000 && !tilt) {
    pwmWrite(3, DEFAULT_VAL);
    pwmWrite(9, DEFAULT_VAL);
    tilt = true;
  }
  if (now - lastSensor > SENSOR_INTERVAL) {
    int val = analogRead(A0);
    Serial.write('!');
    Serial.write(val >> 8);
    Serial.write((byte)val);
    lastSensor += SENSOR_INTERVAL;
  }
  
}
