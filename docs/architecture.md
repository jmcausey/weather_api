# Architecture and Code Map

## Overview

`weather_api` is a Flask application that exposes JSON endpoints under `/api/v1`. PostgreSQL stores location metadata, current-weather history, forecast snapshots, and scheduled jobs. OpenWeatherMap supplies current conditions, geocoding fallback, and forecast periods.

The Docker Compose project runs three services:

1. **postgres** — PostgreSQL 16 database.
2. **api** — Gunicorn serving the Flask application.
3. **scheduler** — a long-running process that checks and executes due weather jobs.

The API and scheduler use the same database and OpenWeatherMap API key.

## Request and collection flows

### Current weather request

1. A client calls `GET /api/v1/weather` with a location or coordinates.
2. The weather service resolves the location to coordinates if necessary.
3. It requests current conditions from OpenWeatherMap.
4. The response is normalized into the application's JSON shape.
5. The API returns the normalized result. This read endpoint does not itself save a sample.

To retrieve and persist a current sample in one call, use `POST /api/v1/weather/collect`, or configure a scheduled `current` job.

### Forecast request and snapshot collection

1. A client calls `GET /api/v1/forecast`, or a scheduled `forecast` job becomes due.
2. The service fetches OpenWeatherMap forecast periods (normally in three-hour steps).
3. Each period includes a forecast-valid timestamp (`valid_at`).
4. Scheduled collection stores all returned periods in `weather_forecasts` with a shared retrieval timestamp (`snapshot_at`).

A later forecast run inserts a new snapshot rather than replacing earlier forecasts. This allows forecasts to be compared with later current-weather samples. The API's forecast read endpoint does not save data.

### Location resolution

- `weather_api/locations.py` searches the PostgreSQL `locations` table.
- A local canonical name match is used before external geocoding.
- If no local match exists, OpenWeatherMap's direct geocoding endpoint is used when `OPENWEATHER_API_KEY` is configured.
- When coordinates are provided directly, geocoding is skipped.

## Source file map

| File | Responsibility |
|---|---|
| `app.py` | WSGI entry point; creates the Flask application. |
| `scheduler.py` | Polling loop for scheduled weather jobs; checks every 30 seconds. |
| `weather_api/__init__.py` | Flask app factory, environment configuration, DB initialization, and blueprint registration. |
| `weather_api/routes.py` | HTTP routes, input validation, JSON responses, and error handling. |
| `weather_api/weather.py` | OpenWeatherMap requests, normalization, dew-point calculation, and persistence of current and forecast data. |
| `weather_api/locations.py` | Imports/searches location and state datasets and resolves canonical locations. |
| `weather_api/tasks.py` | Executes jobs, determines which jobs are due, and records job status/errors. |
| `weather_api/db.py` | PostgreSQL connection lifecycle, table/index creation, and dataset initialization. |
| `data/locations/locations.json` | Canonical display names mapped to latitude/longitude pairs. |
| `data/locations/states.json` | US state names and abbreviations for state-name searches. |
| `docker-compose.yml` | PostgreSQL, API, and scheduler services. |
| `Dockerfile` | Image definition used by API and scheduler containers. |

## Application lifecycle

The app factory `create_app()` reads configuration from environment variables, registers a teardown handler for the database connection, initializes tables and location datasets, and registers the API blueprint. The scheduler creates its own app and enters an application context for each polling cycle.

Database initialization uses `CREATE TABLE IF NOT EXISTS` and adds `weather_jobs.job_type` with `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` so an existing installation can be upgraded without dropping existing rows.

## Important semantics

- Current weather is supplied by a weather API; it should not be treated as a quality-controlled station observation.
- Forecast `snapshot_at` means when the forecast was retrieved and stored. `valid_at` means the time the forecast predicts conditions for.
- API calls can fail because of missing credentials, provider errors, invalid coordinates, or database availability. Inspect the JSON error and service logs.
