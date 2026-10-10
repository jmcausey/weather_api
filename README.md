# weather_api

API-only weather service migrated from jmcausey/weather.

## Documentation

Detailed Markdown documentation is in [docs/](docs/README.md):

- [Architecture and code map](docs/architecture.md)
- [HTTP API reference](docs/api-reference.md)
- [Database schema](docs/database.md)
- [Configuration and deployment](docs/configuration.md)

## Endpoints

- GET /api/v1/health
- GET /api/v1/locations?q=Seattle&limit=20
- GET /api/v1/weather?location=Seattle,WA
- GET /api/v1/forecast?location=Seattle,WA
- POST /api/v1/weather/collect
- GET /api/v1/history?location=Seattle,WA&limit=50
- GET /api/v1/forecasts?location=Seattle,%20WA&limit=100
- GET /api/v1/jobs
- POST /api/v1/jobs
- DELETE /api/v1/jobs/{id}
- POST /api/v1/jobs/{id}/run

## Locations

The repository includes data/locations/locations.json, containing location names and coordinates, and data/locations/states.json for US state-name searching. PostgreSQL loads these datasets on startup.

## Scheduled collection

The scheduler container polls enabled weather_jobs every 30 seconds and runs jobs when their interval is due. A job can collect either current weather or forecast snapshots. Current conditions are stored in the existing chart table. Forecast collection stores every forecast period returned by OpenWeatherMap in weather_forecasts, with both the retrieval time (snapshot_at) and forecast-valid time (valid_at).

Forecast snapshots are retained instead of overwritten so later you can compare what a forecast predicted with what actually happened. Current conditions from a weather API are not necessarily quality-controlled weather-station observations.

The examples below use Seattle, WA (latitude 47.6062, longitude -122.3321).

Create an hourly current-weather job for Seattle, WA:

    curl -sS -X POST http://localhost:5000/api/v1/jobs \
      -H 'Content-Type: application/json' \
      -d '{"name":"Seattle hourly current weather","location":"Seattle, WA","latitude":47.6062,"longitude":-122.3321,"interval_minutes":60,"job_type":"current","enabled":true}'

Create a forecast job that refreshes every four hours:

    curl -sS -X POST http://localhost:5000/api/v1/jobs \
      -H 'Content-Type: application/json' \
      -d '{"name":"Seattle forecast every 4 hours","location":"Seattle, WA","latitude":47.6062,"longitude":-122.3321,"interval_minutes":240,"job_type":"forecast","enabled":true}'

New jobs are eligible on the next scheduler poll. Inspect jobs and their last status with:

    curl -sS http://localhost:5000/api/v1/jobs

Inspect stored actual-weather samples and forecast snapshots with:

    curl -sS 'http://localhost:5000/api/v1/history?location=Seattle%2C%20WA&limit=10'
    curl -sS 'http://localhost:5000/api/v1/forecasts?location=Seattle%2C%20WA&limit=20'

Use last_status and last_error on each job to troubleshoot collection. Allowed intervals are 15, 60, 240, and 1440 minutes.

## Docker

    cp .env.example .env
    # set OPENWEATHER_API_KEY and matching PostgreSQL credentials
    docker compose up -d --build

The existing PostgreSQL chart and weather_jobs tables are retained. Startup adds the job_type column to existing installations and creates weather_forecasts without dropping data.
