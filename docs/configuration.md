# Configuration and Deployment

## Requirements

- Docker Engine and Docker Compose plugin for the recommended deployment.
- An OpenWeatherMap API key for live weather, forecasts, and external geocoding fallback.
- The bundled location datasets at `data/locations/locations.json` and `data/locations/states.json`.

## Environment variables

| Variable | Used by | Description |
|---|---|---|
| `DATABASE_URL` | API and scheduler | PostgreSQL connection string. In Docker Compose this is built from the PostgreSQL environment values and points to host `postgres:5432`. |
| `POSTGRES_USER` | PostgreSQL / Compose | Database role. Default in Compose: `weather`; `.env.example` currently sets `cl`. |
| `POSTGRES_PASSWORD` | PostgreSQL / Compose | Password for the database role. Set a secure value outside local development. |
| `POSTGRES_DB` | PostgreSQL / Compose | Database name. Default in Compose: `weather`; `.env.example` currently sets `cl`. |
| `OPENWEATHER_API_KEY` | API and scheduler | API credential for OpenWeatherMap. Required for weather/forecast calls and external geocoding fallback. |
| `APP_PORT` | Compose | Host port mapped to container port 5000. The `.env.example` currently uses `5002`. |
| `CURRENT_LOCATION` | Flask config | Optional config value available to the app; current routes use explicit request locations/coordinates. |

The app factory also has a development fallback `DATABASE_URL` of `postgresql://cl:change-me@localhost:5432/cl`. In container deployment, Compose sets `DATABASE_URL` explicitly.

## Start with Docker Compose

1. Copy the example environment file:

   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and set a secure PostgreSQL password plus your OpenWeatherMap key. Keep the PostgreSQL username/database consistent with any existing deployment you intend to use.

3. Build and start services:

   ```bash
   docker compose up -d --build
   ```

4. Inspect service status and logs:

   ```bash
   docker compose ps
   docker compose logs --tail=100 api scheduler
   ```

5. Test the API:

   ```bash
   curl -sS http://localhost:${APP_PORT:-5002}/api/v1/health
   curl -sS 'http://localhost:${APP_PORT:-5002}/api/v1/locations?q=Seattle&limit=5'
   ```

The port in the URL is the host port configured by `APP_PORT`. If the variable is not set in the environment file, Compose's default is 5000.

## Services and persistence

- `postgres` uses PostgreSQL 16 and a named volume, `weather_api_postgres_data`.
- `api` runs Gunicorn with two workers and listens on container port 5000.
- `scheduler` runs `python scheduler.py` and polls every 30 seconds.
- PostgreSQL's health check gates startup of API and scheduler containers.
- Use `docker compose down` to stop and remove containers/network while retaining the named database volume.
- **Do not run `docker compose down -v` unless you intend to delete the named database volume and its data.**

## Updating an existing database

Startup creates missing tables and indexes and adds the `job_type` column to `weather_jobs` if absent. It does not drop existing tables. The database credentials in Compose must match the intended database. Changing `POSTGRES_USER` or `POSTGRES_DB` does not automatically rewrite an already-initialized PostgreSQL data directory.

The location catalog is imported only if `locations` is empty. State names/abbreviations are upserted during startup.

## Troubleshooting

### Health endpoint returns database unavailable

Check that PostgreSQL is healthy, the database URL credentials match, and the API can reach the `postgres` service:

```bash
docker compose ps
docker compose logs --tail=100 postgres api
```

### Weather calls report missing API key or provider errors

Set `OPENWEATHER_API_KEY` in `.env`, then recreate the containers so they receive the updated environment:

```bash
docker compose up -d --build api scheduler
docker compose logs --tail=100 api scheduler
```

### Location dataset not found

The container expects these repository paths:

- `data/locations/locations.json`
- `data/locations/states.json`

Ensure both files are present in the build context and copied into the image by the Dockerfile.

### Scheduled job is failing

Read the job's `last_status` and `last_error` from `GET /api/v1/jobs`, then inspect scheduler logs. The scheduler polls every 30 seconds, but a job only runs when its interval is due or when it is triggered manually with `POST /api/v1/jobs/{id}/run`.

### API port is already in use

Choose an unused host port in `.env` using `APP_PORT`, then restart the Compose project. The internal API port remains 5000.
