# weather_api

API-only migration of the weather service from jmcausey/weather.

## Endpoints

- GET /api/v1/health
- GET /api/v1/weather?location=Athens,TX
- GET /api/v1/weather?latitude=32.2049&longitude=-95.8555
- GET /api/v1/forecast?location=Athens,TX
- POST /api/v1/weather/collect
- GET /api/v1/history?location=Athens,TX&limit=50
- GET /api/v1/jobs
- POST /api/v1/jobs
- DELETE /api/v1/jobs/{id}
- POST /api/v1/jobs/{id}/run

The API uses OpenWeather for current conditions and forecasts and PostgreSQL for collected history and scheduled jobs.

## Docker

Designed to share the PostgreSQL server and cl_shared_data Docker network used by jmcausey/cl.

    cp .env.example .env
    # set OPENWEATHER_API_KEY and matching PostgreSQL credentials
    docker compose up -d --build

Test:

    curl http://localhost:5002/api/v1/health
    curl "http://localhost:5002/api/v1/weather?location=Athens,TX"
    curl "http://localhost:5002/api/v1/history?location=Athens,TX&limit=10"

## Data compatibility

The existing PostgreSQL chart and weather_jobs tables are retained. The API initializes them if they do not exist, so existing weather history remains available to the new service.

The old HTML templates, static assets, pandas, matplotlib, and UI/control-panel routes are intentionally not part of this repository.
