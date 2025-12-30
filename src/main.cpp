#include <Arduino.h>
#include <Wire.h>
#include <TinyGPS++.h>
#include <cmath>
// Сначала подключаем модель!
#include "model_data.h"
#include <EloquentTinyML.h>

// --- CONFIG ---
#define SERIAL_BAUD 921600
#define SDA_PIN 8
#define SCL_PIN 9
#define MPU_ADDR 0x68
#define GPS_RX 4
#define GPS_TX 5

// MIC
#define MIC_PIN 1 

// AI SETTINGS
#define N_INPUTS 3
#define N_OUTPUTS 3
#define TENSOR_ARENA 2 * 1024

Eloquent::TinyML::TfLite<N_INPUTS, N_OUTPUTS, TENSOR_ARENA> ml;

TinyGPSPlus gps;
HardwareSerial ss(1);
SemaphoreHandle_t dataMutex;

volatile float sh_r=0, sh_p=0, sh_acc=0, sh_noise=0;
volatile float ai_safe=100;
volatile int ai_stat=0;
bool armed = false;

// ==========================================
// TASK AI
// ==========================================
void TaskAI(void *pvParameters) {
  // Запускаем модель
  if (!ml.begin((unsigned char*)model_tflite)) {
    Serial.println("AI LOAD ERROR!");
  } else {
    Serial.println("AI ONLINE");
  }

  for (;;) {
    float r, p, acc;
    if (xSemaphoreTake(dataMutex, 10) == pdTRUE) {
      r = sh_r; p = sh_p; acc = sh_acc;
      xSemaphoreGive(dataMutex);
    }

    float input[3] = { r, p, acc };
    float output[3] = { 0, 0, 0 };
    ml.predict(input, output);

    int status = 0;
    if (output[1] > 0.6) status = 1;
    if (output[2] > 0.7) status = 2;
    float score = (1.0 - output[2]) * 100.0;

    if (xSemaphoreTake(dataMutex, 10) == pdTRUE) {
      ai_safe = score; ai_stat = status;
      xSemaphoreGive(dataMutex);
    }

    vTaskDelay(20);
  }
}

// ==========================================
// SETUP & LOOP
// ==========================================
void setup() {
  Serial.begin(SERIAL_BAUD);
  dataMutex = xSemaphoreCreateMutex();
  ss.begin(9600, SERIAL_8N1, GPS_RX, GPS_TX);
  
  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(400000); 
  delay(200);
  Wire.beginTransmission(MPU_ADDR); Wire.write(0x6B); Wire.write(0); Wire.endTransmission();

  xTaskCreatePinnedToCore(TaskAI, "Brain", 10000, NULL, 1, NULL, 0);
}

void loop() {
  if (Serial.available()) {
    String c = Serial.readStringUntil('\n');
    if (c.indexOf("ARM") >= 0) armed = true;
    if (c.indexOf("DISARM") >= 0) armed = false;
  }

  while (ss.available()) gps.encode(ss.read());

  Wire.beginTransmission(MPU_ADDR); Wire.write(0x3B); Wire.endTransmission(false);
  
  Wire.requestFrom((uint16_t)MPU_ADDR, (uint8_t)6, true);

  int raw_mic = analogRead(MIC_PIN);
  float noise = raw_mic / 40.95;

  if (Wire.available() >= 6) {
    int16_t AcX = Wire.read()<<8 | Wire.read();
    int16_t AcY = Wire.read()<<8 | Wire.read();
    int16_t AcZ = Wire.read()<<8 | Wire.read();
    
    float r = atan2(AcY, AcZ) * 57.3;
    float p = atan2(-AcX, sqrt((long)AcY*AcY + (long)AcZ*AcZ)) * 57.3;
    float g = sqrt((long)AcX*AcX + (long)AcY*AcY + (long)AcZ*AcZ) / 16384.0;

    if (xSemaphoreTake(dataMutex, 5) == pdTRUE) {
      sh_r = r; sh_p = p; sh_acc = g; sh_noise = noise;
      xSemaphoreGive(dataMutex);
    }

    float sc = 100; int st = 0;
    if (xSemaphoreTake(dataMutex, 5) == pdTRUE) {
      sc = ai_safe; st = ai_stat;
      xSemaphoreGive(dataMutex);
    }

    // ИСПРАВЛЕННАЯ СТРОКА: Добавлены lat и lon
    Serial.printf("{\"r\":%.1f,\"p\":%.1f,\"lat\":%.6f,\"lon\":%.6f,\"alt\":%.0f,\"as\":%.0f,\"st\":%d,\"arm\":%d,\"sd\":%d,\"noise\":%.0f}\n", 
                  r, p, 
                  gps.location.lat(), gps.location.lng(), 
                  gps.altitude.meters(), 
                  sc, st, armed, 0, noise);
  }
  delay(10); 
}