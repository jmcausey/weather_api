/*
 * Adafruit ESP32-S2 Feather + BME280 weather station
 *
 * Arduino IDE libraries:
 *   - Adafruit BME280 Library
 *   - Adafruit Unified Sensor
 *
 * Configure Wi-Fi and API settings below before uploading.
 * This starter sketch uses plain HTTP for a trusted LAN only. Do not expose
 * the endpoint/device key to the public internet. HTTPS certificate validation
 * requires a WiFiClientSecure configuration and is not implemented here.
 */
#include <WiFi.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <Adafruit_BME280.h>
#include <Adafruit_Sensor.h>
#include <time.h>

const char* WIFI_SSID = "CHANGE_ME";
const char* WIFI_PASSWORD = "CHANGE_ME";

// Use your server's LAN IP and actual published APP_PORT, not localhost.
const char* API_URL = "http://192.168.1.20:5002/api/v1/sensors/observations";
const char* SENSOR_API_KEY = "CHANGE_ME_TO_A_LONG_RANDOM_SECRET";
const char* STATION_ID = "home-weather-01";

const unsigned long SAMPLE_INTERVAL_MS = 60000UL;
const int I2C_SDA_PIN = SDA;
const int I2C_SCL_PIN = SCL;

Adafruit_BME280 bme;
unsigned long lastSendMs = 0;
bool bmeReady = false;

String utcTimestamp() {
  struct tm timeinfo;
  if (!getLocalTime(&timeinfo, 1000)) return "";
  char buffer[25];
  strftime(buffer, sizeof(buffer), "%Y-%m-%dT%H:%M:%SZ", &timeinfo);
  return String(buffer);
}

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to Wi-Fi");
  unsigned long started = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - started < 20000UL) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("Wi-Fi connected; IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("Wi-Fi connection timed out; will retry.");
  }
}

bool postObservation() {
  if (!bmeReady) return false;
  connectWiFi();
  if (WiFi.status() != WL_CONNECTED) return false;

  String observedAt = utcTimestamp();
  if (observedAt.length() == 0) {
    Serial.println("Waiting for NTP time synchronization.");
    return false;
  }

  // Add optional wind_speed_mps, wind_direction_deg, rainfall_mm, and/or
  // rainfall_total_mm when those sensors are installed.
  String body = "{";
  body += "\"station_id\":\"" + String(STATION_ID) + "\",";
  body += "\"observed_at\":\"" + observedAt + "\",";
  body += "\"temperature_c\":" + String(bme.readTemperature(), 2) + ",";
  body += "\"humidity_pct\":" + String(bme.readHumidity(), 2) + ",";
  body += "\"pressure_hpa\":" + String(bme.readPressure() / 100.0F, 2);
  body += "}";

  HTTPClient http;
  http.setTimeout(8000);
  if (!http.begin(API_URL)) {
    Serial.println("Could not initialize HTTP client.");
    return false;
  }
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Sensor-API-Key", SENSOR_API_KEY);
  int status = http.POST(body);
  String response = http.getString();
  http.end();

  Serial.printf("POST status: %d\n", status);
  if (response.length()) Serial.println(response);
  return status >= 200 && status < 300;
}

void setup() {
  Serial.begin(115200);
  delay(300);
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);

  bmeReady = bme.begin(0x77, &Wire);
  if (!bmeReady) bmeReady = bme.begin(0x76, &Wire);
  if (!bmeReady) Serial.println("BME280 not found at I2C addresses 0x77 or 0x76.");

  connectWiFi();
  configTime(0, 0, "pool.ntp.org", "time.nist.gov");
}

void loop() {
  unsigned long now = millis();
  if (now - lastSendMs >= SAMPLE_INTERVAL_MS) {
    lastSendMs = now;
    if (postObservation()) Serial.println("Observation accepted.");
    else Serial.println("Observation not sent; next scheduled attempt will retry.");
  }
  delay(50);
}
