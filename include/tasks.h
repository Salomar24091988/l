#pragma once

#include <Arduino.h>
#if defined(ESP32)
  #include <WiFi.h>
#else
  #include <ESP8266WiFi.h>
#endif
#include "secrets.h"

// FreeRTOS task handles (ESP32 only)
#if defined(ESP32)
extern TaskHandle_t elegantOTATaskHandle;
#endif

// WiFi configuration structure
struct WiFiConfig {
  char ssid[32];
  char password[64];
  bool enabled;
};

// WiFi settings structure for LittleFS storage
struct WiFiSettings {
  WiFiConfig networks[3];  // Up to 3 configurable networks
  bool fallbackEnabled;    // Use secrets.h fallback
  uint8_t currentNetwork;  // Currently selected network index
};

// Global settings
extern WiFiSettings wifiSettings;
extern bool otaInProgress;
extern bool captivePortalActive;

extern volatile bool is_rotating;
extern float gyro_threshold;

// DNS server constants
extern const byte DNS_PORT;
extern IPAddress apIP;
extern IPAddress netMask;

// Task declarations
#if defined(ESP32)
void elegantOTATask(void *parameter);
#endif

// Web server setup + per-iteration servicing (platform-neutral)
void setupWebServer();
void webServerLoop();

// WiFi management functions
bool initWiFi();
bool connectToWiFi(const char* ssid, const char* password);
void startCaptivePortal();
void stopCaptivePortal();
void saveWiFiSettings();
bool loadWiFiSettings();
void resetWiFiSettings();

// LittleFS helpers
bool initLittleFS();
String readFile(const char* path);
bool writeFile(const char* path, const String& content);

// Template processor for index.html
String processor(const String& var);
