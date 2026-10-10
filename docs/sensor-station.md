# ESP32 Weather Station

This guide adds an Adafruit ESP32-S2 Feather with a BME280 as a sensor source separate from OpenWeatherMap. It is designed to accommodate later wind-speed, wind-direction, and rainfall instruments without changing the basic observation model.

## Data model

Every observation has a `station_id` and an observation timestamp. Measurements are nullable so a station can report only the sensors currently installed.

| Field | Unit | Meaning |
|---|---|---|
| `temperature_c` | °C | BME280 ambient temperature |
| `humidity_pct` | % RH | Relative humidity |
| `pressure_hpa` | hPa | Absolute barometric pressure from the BME280 |
| `wind_speed_mps` | m/s | Future wind-speed sensor |
| `wind_direction_deg` | degrees | Future direction, clockwise from north (0–359) |
| `rainfall_mm` | mm | Rain accumulated during the observation interval |
| `rainfall_total_mm` | mm | Optional cumulative rain counter since station reset |
| `observed_at` | ISO 8601 UTC | When the station measured the conditions |

Do not infer wind or rain as zero when those sensors are absent; omit the field or send `null`.

## Configure the API

1. Set `SENSOR_INGEST_API_KEY` in the private `.env` to a long random secret.
2. Ensure the API and scheduler containers receive this environment variable (Compose does this for both).
3. Rebuild/restart the API after changing the environment:

   ```bash
   docker compose up -d --build
   ```

4. Keep the API key out of Git and never commit your real `.env`.

The first implementation uses one shared ingestion key for the station endpoint. Treat it as a device credential: store it privately in firmware configuration and rotate it if the device is lost or compromised. A later iteration can support per-station credentials.

## Upload Arduino firmware

Open `firmware/esp32_s2_bme280/esp32_s2_bme280.ino` in Arduino IDE.

Install these libraries using Library Manager:

- Adafruit BME280 Library
- Adafruit Unified Sensor

Select the Adafruit ESP32-S2 Feather board. Edit `WIFI_SSID`, `WIFI_PASSWORD`, `API_URL`, and `SENSOR_API_KEY` before upload. The example tries I²C addresses 0x77 and 0x76. Check your breakout's wiring and I²C address if initialization fails.

Set `API_URL` to the API host reachable from the ESP32. Do not use `localhost`: on the ESP32, that means the ESP32 itself. For a server on your home network, use its LAN address, for example `http://192.168.1.20:5000/api/v1/sensors/observations`. Plain HTTP is suitable only for a trusted isolated LAN; use HTTPS with certificate validation for remote/public access. Do not expose this endpoint to the internet over plain HTTP.

The firmware sends a reading once per minute and uses NTP to create UTC timestamps. If Wi-Fi or the API is unavailable, it logs the failure and retries on the next interval; this starter firmware does not persist a queue across power loss.

## Test ingestion manually

Use the same API key configured in `.env`:

```bash
curl -sS -X POST http://localhost:5000/api/v1/sensors/observations \
  -H 'Content-Type: application/json' \
  -H 'X-Sensor-API-Key: YOUR_SENSOR_INGEST_API_KEY' \
  -d '{
    "station_id": "home-weather-01",
    "observed_at": "2026-10-10T18:30:00Z",
    "temperature_c": 23.7,
    "humidity_pct": 54.2,
    "pressure_hpa": 1013.4
  }'
```

Check the latest sample and recent history:

```bash
curl -sS http://localhost:5000/api/v1/sensors/home-weather-01/latest
curl -sS 'http://localhost:5000/api/v1/sensors/home-weather-01/history?limit=20'
```

The sample values above are illustrative, not real readings.

## Future sensor expansion

The API payload and database already reserve optional fields for the following additions:

- Wind speed: use `wind_speed_mps` and convert pulses to m/s in the microcontroller firmware.
- Wind direction: use `wind_direction_deg` in degrees clockwise from true/north reference as defined by the sensor installation. Apply a calibration offset if required.
- Rain gauge: send `rainfall_mm` for each reporting interval, and optionally `rainfall_total_mm` for the station's cumulative counter.

For a tipping-bucket gauge, count switch transitions with a debounced interrupt or pulse counter and convert each tip using the gauge manufacturer's mm-per-tip calibration. Preserve the interval amount separately from the cumulative total. On reboot, the cumulative total may reset unless persisted; consumers should use interval rainfall for straightforward aggregation.

## Security and reliability notes

- The ingestion endpoint rejects requests without the configured key.
- Use a long random key; do not reuse your OpenWeatherMap key or database password.
- Keep the API bound to a trusted network unless HTTPS and appropriate access controls are configured.
- Validate timestamps and ranges; sensor measurements are not treated as quality-controlled official observations.
- This initial firmware does not have offline flash queueing, per-station secrets, OTA updates, or deep-sleep scheduling yet.
