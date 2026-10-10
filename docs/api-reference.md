# HTTP API Reference

All endpoints are prefixed with `/api/v1` and return JSON. Examples assume the API is available at `http://localhost:5000`.

## Common behavior

- JSON request bodies should use `Content-Type: application/json`.
- Location names should match the canonical display name where possible, such as `Seattle, WA`.
- Alternatively, supply both `latitude` and `longitude`.
- `limit` parameters are bounded by the server to avoid unbounded result sets.
- Validation errors generally return HTTP 400; missing local/external locations return 404; provider or collection failures return 502; health-check database failures return 503.

## Health

### `GET /api/v1/health`

Checks database connectivity.

Example:

```bash
curl -sS http://localhost:5000/api/v1/health
```

Successful response:

```json
{"status":"ok"}
```

A database connection failure returns HTTP 503 with an error message.

## Locations

### `GET /api/v1/locations`

Searches the local location dataset imported into PostgreSQL.

| Parameter | Default | Description |
|---|---:|---|
| `q` | empty | Case-insensitive partial match against display name, city/name, region abbreviation, or full US state name. |
| `limit` | 50 | Result count, clamped to 1–500. |

Examples:

```bash
curl -sS 'http://localhost:5000/api/v1/locations?q=Seattle&limit=20'
curl -sS 'http://localhost:5000/api/v1/locations?q=Washington&limit=20'
```

Response shape:

```json
{
  "count": 1,
  "items": [
    {
      "display_name": "Seattle, WA",
      "name": "Seattle",
      "region": "WA",
      "latitude": 47.6062,
      "longitude": -122.3321
    }
  ]
}
```

The returned number of rows depends on the bundled dataset and search query.

## Current weather

### `GET /api/v1/weather`

Fetches current conditions from OpenWeatherMap and normalizes the result. It does **not** save a history sample.

Provide either `location` or both `latitude` and `longitude`.

Examples:

```bash
curl -sS 'http://localhost:5000/api/v1/weather?location=Seattle%2C%20WA'
curl -sS 'http://localhost:5000/api/v1/weather?latitude=47.6062&longitude=-122.3321'
```

Typical response fields include:

- `location`, `observed_location`, `country`
- `latitude`, `longitude`
- `description`, `temperature`, `feels_like`, `pressure`, `humidity`
- `visibility`, `wind_speed`, `wind_direction`, `clouds`
- `sunrise`, `sunset`, `dew_point`

Temperatures and wind speed use OpenWeatherMap's imperial units configuration.

## Forecast

### `GET /api/v1/forecast`

Fetches the forecast periods currently returned by OpenWeatherMap. It does **not** store them.

Provide either `location` or both coordinates.

```bash
curl -sS 'http://localhost:5000/api/v1/forecast?location=Seattle%2C%20WA'
curl -sS 'http://localhost:5000/api/v1/forecast?latitude=47.6062&longitude=-122.3321'
```

The response includes provider/location metadata and a `points` array. Each point includes `time` (in the provider city's local timezone), `valid_at` (UTC ISO timestamp), temperature, feels-like temperature, pressure, description/icon, precipitation probability/amount, humidity, wind, and cloud cover.

## Collect current weather

### `POST /api/v1/weather/collect`

Fetches current weather and inserts it into the `chart` history table.

Request body:

```json
{
  "location": "Seattle, WA",
  "latitude": 47.6062,
  "longitude": -122.3321
}
```

Either `location` or both coordinates are required. When both a location and coordinates are supplied, the coordinates are used for the weather request while the supplied location labels the result.

```bash
curl -sS -X POST http://localhost:5000/api/v1/weather/collect \
  -H 'Content-Type: application/json' \
  -d '{"location":"Seattle, WA","latitude":47.6062,"longitude":-122.3321}'
```

Success returns the normalized sample with HTTP 201.

## Current-weather history

### `GET /api/v1/history`

Reads saved samples from `chart`.

| Parameter | Default | Description |
|---|---:|---|
| `location` | empty | Optional exact location filter. |
| `limit` | 50 | Result count, clamped to 1–500. |

```bash
curl -sS 'http://localhost:5000/api/v1/history?location=Seattle%2C%20WA&limit=10'
```

Response shape: `{"count": ..., "items": [...]}`. Each item includes the sample timestamp and current-weather fields such as temperature, humidity, pressure, wind, cloud cover, sunrise/sunset, and dew point.

## Stored forecast snapshots

### `GET /api/v1/forecasts`

Reads previously stored forecast periods from `weather_forecasts`. It does not call the provider.

| Parameter | Default | Description |
|---|---:|---|
| `location` | empty | Optional exact location filter. |
| `limit` | 100 | Result count, clamped to 1–1000. |

```bash
curl -sS 'http://localhost:5000/api/v1/forecasts?location=Seattle%2C%20WA&limit=20'
```

Rows are ordered by newest `snapshot_at` first and then earliest `valid_at` within each snapshot. Important fields are `provider`, `snapshot_at`, `valid_at`, and the predicted weather values.

## Scheduled jobs

### `GET /api/v1/jobs`

Lists all scheduled jobs, with enabled jobs first.

```bash
curl -sS http://localhost:5000/api/v1/jobs
```

Each job includes its ID, name, location, coordinates, interval, `job_type`, enabled state, and last-run status/error fields.

### `POST /api/v1/jobs`

Creates a job. Required fields: `name`, `location`, `latitude`, `longitude`, and `interval_minutes`. Optional fields: `job_type` (defaults to `current`) and `enabled` (defaults to `true`).

Allowed intervals are **15, 60, 240, and 1440 minutes**. `job_type` must be `current` or `forecast`.

Example current job, hourly:

```bash
curl -sS -X POST http://localhost:5000/api/v1/jobs \
  -H 'Content-Type: application/json' \
  -d '{"name":"Seattle hourly current weather","location":"Seattle, WA","latitude":47.6062,"longitude":-122.3321,"interval_minutes":60,"job_type":"current","enabled":true}'
```

Example forecast job, every four hours:

```bash
curl -sS -X POST http://localhost:5000/api/v1/jobs \
  -H 'Content-Type: application/json' \
  -d '{"name":"Seattle forecast every 4 hours","location":"Seattle, WA","latitude":47.6062,"longitude":-122.3321,"interval_minutes":240,"job_type":"forecast","enabled":true}'
```

New jobs with no previous run are eligible on the next scheduler poll. Job creation returns the inserted job with HTTP 201.

### `POST /api/v1/jobs/{id}/run`

Runs an enabled job immediately. Replace `{id}` with the numeric job ID.

```bash
curl -sS -X POST http://localhost:5000/api/v1/jobs/1/run
```

Returns `{"id": 1, "status": "completed"}` on success. If the job fails, the endpoint returns HTTP 502; inspect `last_error` via `GET /api/v1/jobs`.

### `DELETE /api/v1/jobs/{id}`

Deletes a job definition. It does not delete already-collected current history or forecast snapshots.

```bash
curl -sS -X DELETE http://localhost:5000/api/v1/jobs/1
```

Successful response: `{"deleted": 1}`. Unknown IDs return HTTP 404.
