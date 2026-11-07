I reviewed the current `main` branch of [jmcausey/weather_api](https://github.com/jmcausey/weather_api?utm_source=chatgpt.com), including its README and `docs/api-reference.md`.

Below is an expanded API curl reference covering all documented API functions, with examples using your local Docker deployment at `localhost:5000` and Seattle, WA as the example location.

# Weather API – Complete cURL Reference



13 documented endpoint operations

API v1



# Weather API – cURL Command Reference

Repository: [https://github.com/jmcausey/weather_api](https://github.com/jmcausey/weather_api)

Base URL: `http://localhost:5000`

API prefix: `/api/v1`

Example location: Seattle, WA\
Latitude: `47.6062`\
Longitude: `-122.3321`

---

## 1. Environment Setup

Define reusable shell variables:

```
export API="http://localhost:5000"
export API_V1="$API/api/v1"
export LOCATION="Seattle, WA"
export LAT="47.6062"
export LON="-122.3321"
```

For formatted JSON output, pipe requests through `jq`.

---

## 2. Health and Status

### Check API and database health

```
curl -sS "$API_V1/health" | jq
```

### Expected response

```
{
  "status": "ok"
}
```

---

## 3. Location Functions

### Search for a city

```
curl -sS "$API_V1/locations?q=Seattle" | jq
```

### Search for a state

```
curl -sS "$API_V1/locations?q=Washington" | jq
```

### Limit search results

```
curl -sS "$API_V1/locations?q=Texas&limit=20" | jq
```

### Search using a variable

```
curl -sS "$API_V1/locations?q=$LOCATION&limit=10" | jq
```

---

## 4. Current Weather Functions

### Get current weather by location

```
curl -sS -G "$API_V1/weather" \
  --data-urlencode "location=$LOCATION" | jq
```

### Get current weather by coordinates

```
curl -sS "$API_V1/weather?latitude=$LAT&longitude=$LON" | jq
```

### Extract selected weather metrics

```
curl -sS -G "$API_V1/weather" \
  --data-urlencode "location=$LOCATION" |
jq '{
  location,
  temperature,
  feels_like,
  humidity,
  pressure,
  wind_speed,
  wind_direction,
  clouds,
  description,
  sunrise,
  sunset
}'
```

---

## 5. Forecast Functions

### Get forecast by location

```
curl -sS -G "$API_V1/forecast" \
  --data-urlencode "location=$LOCATION" | jq
```

### Get forecast by coordinates

```
curl -sS "$API_V1/forecast?latitude=$LAT&longitude=$LON" | jq
```

### Extract forecast periods

```
curl -sS -G "$API_V1/forecast" \
  --data-urlencode "location=$LOCATION" |
jq '.points[] | {
  time,
  valid_at,
  temperature,
  feels_like,
  humidity,
  wind_speed,
  wind_direction,
  precipitation_probability,
  precipitation,
  description
}'
```

---

## 6. Collect and Store Current Weather

### Manually collect current weather

```
curl -sS -X POST "$API_V1/weather/collect" \
  -H "Content-Type: application/json" \
  -d "{
    \"location\": \"$LOCATION\",
    \"latitude\": $LAT,
    \"longitude\": $LON
  }" | jq
```

This retrieves current conditions and inserts a sample into the PostgreSQL `chart` table.

---

## 7. Current Weather History

### Retrieve latest 50 records

```
curl -sS "$API_V1/history" | jq
```

### Retrieve Seattle history

```
curl -sS -G "$API_V1/history" \
  --data-urlencode "location=$LOCATION" \
  --data-urlencode "limit=50" | jq
```

### Retrieve latest 10 records

```
curl -sS -G "$API_V1/history" \
  --data-urlencode "location=$LOCATION" \
  --data-urlencode "limit=10" | jq
```

### Extract temperature and timestamps

```
curl -sS -G "$API_V1/history" \
  --data-urlencode "location=$LOCATION" \
  --data-urlencode "limit=100" |
jq '.items[] | {
  created_at,
  temperature,
  humidity,
  pressure,
  wind_speed
}'
```

---

## 8. Stored Forecast History

### Retrieve stored forecasts

```
curl -sS "$API_V1/forecasts" | jq
```

### Retrieve Seattle forecasts

```
curl -sS -G "$API_V1/forecasts" \
  --data-urlencode "location=$LOCATION" \
  --data-urlencode "limit=100" | jq
```

### Retrieve latest 20 forecast records

```
curl -sS -G "$API_V1/forecasts" \
  --data-urlencode "location=$LOCATION" \
  --data-urlencode "limit=20" | jq
```

### Extract forecast snapshot information

```
curl -sS -G "$API_V1/forecasts" \
  --data-urlencode "location=$LOCATION" \
  --data-urlencode "limit=100" |
jq '.items[] | {
  provider,
  snapshot_at,
  valid_at,
  temperature,
  humidity,
  wind_speed
}'
```

Important distinction:

- `snapshot_at`: When the forecast was retrieved.
- `valid_at`: When the forecast predicts the weather will occur.

This allows comparisons between previous forecast predictions and actual observations.

---

## 9. Scheduled Job Management

### List all scheduled jobs

```
curl -sS "$API_V1/jobs" | jq
```

### Create hourly current-weather job

```
curl -sS -X POST "$API_V1/jobs" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"Seattle hourly current weather\",
    \"location\": \"$LOCATION\",
    \"latitude\": $LAT,
    \"longitude\": $LON,
    \"interval_minutes\": 60,
    \"job_type\": \"current\",
    \"enabled\": true
  }" | jq
```

### Create four-hour forecast job

```
curl -sS -X POST "$API_V1/jobs" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"Seattle forecast every 4 hours\",
    \"location\": \"$LOCATION\",
    \"latitude\": $LAT,
    \"longitude\": $LON,
    \"interval_minutes\": 240,
    \"job_type\": \"forecast\",
    \"enabled\": true
  }" | jq
```

### Create 15-minute current-weather job

```
curl -sS -X POST "$API_V1/jobs" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"Seattle 15 minute current weather\",
    \"location\": \"$LOCATION\",
    \"latitude\": $LAT,
    \"longitude\": $LON,
    \"interval_minutes\": 15,
    \"job_type\": \"current\",
    \"enabled\": true
  }" | jq
```

### Create daily forecast job

```
curl -sS -X POST "$API_V1/jobs" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"Seattle daily forecast\",
    \"location\": \"$LOCATION\",
    \"latitude\": $LAT,
    \"longitude\": $LON,
    \"interval_minutes\": 1440,
    \"job_type\": \"forecast\",
    \"enabled\": true
  }" | jq
```

### Run a job immediately

Replace `1` with the actual job ID.

```
curl -sS -X POST "$API_V1/jobs/1/run" | jq
```

### Delete a scheduled job

```
curl -sS -X DELETE "$API_V1/jobs/1" | jq
```

Allowed scheduling intervals:

| Minutes | Frequency        |
| ------- | ---------------- |
| 15      | Every 15 minutes |
| 60      | Hourly           |
| 240     | Every 4 hours    |
| 1440    | Daily            |

---

## 10. Local Sensor Station – ESP32/BME280

Sensor endpoints require the `X-Sensor-API-Key` header.

Define the key in your shell:

```
export SENSOR_KEY="YOUR_SENSOR_INGEST_API_KEY"
```

### Submit a sensor observation

```
curl -sS -X POST "$API_V1/sensors/observations" \
  -H "Content-Type: application/json" \
  -H "X-Sensor-API-Key: $SENSOR_KEY" \
  -d '{
    "station_id": "home-weather-01",
    "observed_at": "2026-11-06T18:30:00Z",
    "temperature_c": 23.7,
    "humidity_pct": 54.2,
    "pressure_hpa": 1013.4
  }' | jq
```

### Submit a complete observation

```
curl -sS -X POST "$API_V1/sensors/observations" \
  -H "Content-Type: application/json" \
  -H "X-Sensor-API-Key: $SENSOR_KEY" \
  -d '{
    "station_id": "home-weather-01",
    "observed_at": "2026-11-06T18:30:00Z",
    "temperature_c": 23.7,
    "humidity_pct": 54.2,
    "pressure_hpa": 1013.4,
    "wind_speed_mps": 2.5,
    "wind_direction_deg": 180,
    "rainfall_mm": 0.0,
    "rainfall_total_mm": 12.5
  }' | jq
```

### Get latest station observation

```
curl -sS "$API_V1/sensors/home-weather-01/latest" | jq
```

### Get station history

```
curl -sS "$API_V1/sensors/home-weather-01/history?limit=100" | jq
```

### Get latest 10 sensor observations

```
curl -sS "$API_V1/sensors/home-weather-01/history?limit=10" | jq
```

---

## 11. Useful Combined Diagnostic Commands

### Check API health and scheduled jobs

```
curl -sS "$API_V1/health" | jq
curl -sS "$API_V1/jobs" | jq
```

### Check current conditions and forecast

```
curl -sS -G "$API_V1/weather" \
  --data-urlencode "location=$LOCATION" | jq

curl -sS -G "$API_V1/forecast" \
  --data-urlencode "location=$LOCATION" | jq
```

### Check collected history

```
curl -sS -G "$API_V1/history" \
  --data-urlencode "location=$LOCATION" \
  --data-urlencode "limit=20" | jq
```

### Check stored forecast snapshots

```
curl -sS -G "$API_V1/forecasts" \
  --data-urlencode "location=$LOCATION" \
  --data-urlencode "limit=50" | jq
```

### Check sensor station

```
curl -sS "$API_V1/sensors/home-weather-01/latest" | jq

curl -sS "$API_V1/sensors/home-weather-01/history?limit=50" | jq
```

---

## 12. HTTP Status Codes

| Status | Meaning                                 |
| ------ | --------------------------------------- |
| 200    | Successful GET or operation             |
| 201    | Successfully created or collected       |
| 400    | Invalid request or parameters           |
| 404    | Resource or location not found          |
| 502    | External provider or collection failure |
| 503    | Database or health-check failure        |

## 13. Official Project Documentation

- Repository: [https://github.com/jmcausey/weather_api](https://github.com/jmcausey/weather_api)
- API reference: [https://github.com/jmcausey/weather_api/blob/main/docs/api-reference.md](https://github.com/jmcausey/weather_api/blob/main/docs/api-reference.md)
- Architecture: [https://github.com/jmcausey/weather_api/blob/main/docs/architecture.md](https://github.com/jmcausey/weather_api/blob/main/docs/architecture.md)
- Database schema: [https://github.com/jmcausey/weather_api/blob/main/docs/database.md](https://github.com/jmcausey/weather_api/blob/main/docs/database.md)
- Sensor station: [https://github.com/jmcausey/weather_api/blob/main/docs/sensor-station.md](https://github.com/jmcausey/weather_api/blob/main/docs/sensor-station.md)

A couple of important notes:

- These examples reflect the documented endpoints in the current repository README and API reference, not a claim that every command has been executed against your running server.
- Sensor requests require the separate ingestion key; do not commit that key to GitHub.
- The API distinguishes live provider requests from stored historical records.

Recommended next step: I can turn this into a permanent `docs/curl-reference.md` in your GitHub repository and add a runnable `examples/api-examples.sh` script containing the commands.
