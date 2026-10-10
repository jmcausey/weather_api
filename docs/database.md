# Database Schema

The service uses PostgreSQL. Tables and indexes are created by `weather_api/db.py` during application initialization. Startup does not drop tables or clear stored observations/jobs.

## `locations`

Canonical location catalog loaded from `data/locations/locations.json`.

| Column | Type | Description |
|---|---|---|
| `display_name` | `TEXT PRIMARY KEY` | Canonical label, such as `Seattle, WA`. |
| `name` | `TEXT NOT NULL` | Name portion parsed from the display label. |
| `region` | `TEXT` | Region/state/country suffix parsed after the final comma-space, if present. |
| `latitude` | `DOUBLE PRECISION NOT NULL` | Latitude in decimal degrees. |
| `longitude` | `DOUBLE PRECISION NOT NULL` | Longitude in decimal degrees. |

Indexes: `idx_locations_name` on `name`, and `idx_locations_region` on `region`.

The importer skips malformed coordinate entries. If the table already contains rows, the current implementation leaves the existing location catalog in place rather than reloading it.

## `states`

US state names and abbreviations loaded from `data/locations/states.json`.

| Column | Type | Description |
|---|---|---|
| `name` | `TEXT NOT NULL` | Full state or district name. |
| `abbreviation` | `TEXT PRIMARY KEY` | Two-letter abbreviation. |

On startup, state rows are inserted or updated by abbreviation. The locations search uses this table to support queries such as `q=Washington` as well as `q=WA`.

## `chart`

Historical current-weather samples. This table may predate the API and is retained for compatibility with the existing application database.

| Column | Type | Description |
|---|---|---|
| `id` | `BIGSERIAL PRIMARY KEY` | Sample ID. |
| `created_at` | `TIMESTAMP` | Insert time, defaulting to database current time. |
| `location` | `TEXT NOT NULL` | Requested/display location. |
| `geolocation` | `TEXT` | Coordinates serialized as `latitude,longitude`. |
| `description` | `TEXT` | Provider weather description. |
| `temperature` | `DOUBLE PRECISION` | Temperature. |
| `pressure` | `INTEGER` | Atmospheric pressure from provider. |
| `feelslike` | `DOUBLE PRECISION` | Feels-like temperature. |
| `humidity` | `INTEGER` | Relative humidity percentage. |
| `visibility` | `INTEGER` | Visibility in provider units. |
| `windspeed` | `DOUBLE PRECISION` | Wind speed. |
| `winddirection` | `INTEGER` | Wind direction in degrees. |
| `clouds` | `INTEGER` | Cloud cover percentage. |
| `sunrise`, `sunset` | `TIMESTAMP` | Provider sunrise/sunset times. |
| `dew_point` | `DOUBLE PRECISION` | Dew point calculated from temperature and humidity. |

Index: `idx_chart_location_created` on `(location, created_at DESC)`.

Rows are inserted by `POST /api/v1/weather/collect` and scheduled `current` jobs. `GET /api/v1/weather` alone does not write to this table.

## `weather_jobs`

Definitions and execution status for recurring collection jobs.

| Column | Type | Description |
|---|---|---|
| `id` | `BIGSERIAL PRIMARY KEY` | Job ID. |
| `name` | `TEXT NOT NULL` | Human-readable job name. |
| `location` | `TEXT NOT NULL` | Location label stored with collected data. |
| `latitude`, `longitude` | `DOUBLE PRECISION NOT NULL` | Coordinates to collect. |
| `interval_minutes` | `INTEGER NOT NULL` | Must be 15, 60, 240, or 1440. |
| `enabled` | `BOOLEAN NOT NULL DEFAULT TRUE` | Whether the scheduler should run the job. |
| `last_run_at` | `TIMESTAMP` | Last attempted run time. |
| `last_status` | `TEXT` | Last result, normally `completed` or `failed`. |
| `last_error` | `TEXT` | Error message from the last failed run, otherwise cleared on success. |
| `created_at`, `updated_at` | `TIMESTAMP NOT NULL` | Creation/update timestamps. |
| `job_type` | `TEXT NOT NULL DEFAULT 'current'` | `current` or `forecast`; added compatibly to older databases. |

Index: `idx_weather_jobs_enabled_run` on `(enabled, last_run_at)`.

The schema's interval constraint accepts only 15, 60, 240, and 1440 minutes. The API validates job type and interval before insertion.

## `weather_forecasts`

Append-only collection of forecast periods, grouped by retrieval snapshot.

| Column | Type | Description |
|---|---|---|
| `id` | `BIGSERIAL PRIMARY KEY` | Row ID. |
| `location` | `TEXT NOT NULL` | Location label. |
| `provider` | `TEXT NOT NULL` | Forecast provider identifier, currently `openweathermap`. |
| `snapshot_at` | `TIMESTAMPTZ NOT NULL` | UTC time when the forecast response was collected. |
| `valid_at` | `TIMESTAMPTZ NOT NULL` | UTC time the forecast period predicts. |
| `temperature`, `feels_like` | `DOUBLE PRECISION` | Forecast temperatures. |
| `pressure` | `INTEGER` | Forecast pressure. |
| `description` | `TEXT` | Forecast description. |
| `precipitation_probability` | `DOUBLE PRECISION` | Probability in percent. |
| `precipitation_amount` | `DOUBLE PRECISION` | Combined rain/snow amount when supplied by the provider. |
| `humidity` | `INTEGER` | Forecast relative humidity. |
| `wind_speed` | `DOUBLE PRECISION` | Forecast wind speed. |
| `wind_direction` | `INTEGER` | Wind direction in degrees. |
| `clouds` | `INTEGER` | Cloud cover percentage. |
| `created_at` | `TIMESTAMPTZ NOT NULL` | Database insertion time. |

Unique constraint: `(location, provider, snapshot_at, valid_at)`. Indexes support lookups by `(location, valid_at)` and `(location, snapshot_at DESC)`.

The same `snapshot_at` is assigned to all periods from one forecast collection. Earlier snapshots are kept so a forecast can later be compared with a saved current-weather sample near the same `valid_at`.

## Transaction and lifecycle notes

- App startup creates missing tables/indexes and commits the schema/data initialization.
- State records are upserted by abbreviation.
- The bundled locations catalog is loaded only when the `locations` table is empty.
- Deleting a `weather_jobs` row removes the schedule definition only; it does not delete weather history or forecast rows.
- No automated retention/purge process is currently defined in the application code.
