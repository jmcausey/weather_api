# weather_api

API-only weather service migrated from jmcausey/weather.

## Endpoints

- GET /api/v1/health
- GET /api/v1/locations?q=Dallas&limit=20
- GET /api/v1/weather?location=Athens,TX
- GET /api/v1/weather?latitude=32.2049&longitude=-95.8555
- GET /api/v1/forecast?location=Athens,TX
- POST /api/v1/weather/collect
- GET /api/v1/history?location=Athens,TX&limit=50
- GET /api/v1/jobs
- POST /api/v1/jobs
- DELETE /api/v1/jobs/{id}
- POST /api/v1/jobs/{id}/run

## Locations

The repository includes `data/locations.json`, containing 10,573 city/location entries as `"Display Name": [latitude, longitude]`.

On application startup, PostgreSQL creates the `locations` table and imports the bundled dataset if the table is empty. The import is protected by a PostgreSQL advisory lock so multiple Gunicorn workers cannot import the dataset concurrently.

The location API searches the imported dataset:

    curl "http://localhost:5002/api/v1/locations?q=Dallas&limit=20"

Weather and forecast requests that provide `location=...` first resolve against this local dataset. If there is no local match, the service falls back to OpenWeather geocoding when `OPENWEATHER_API_KEY` is configured. Requests that provide latitude/longitude continue to use those coordinates directly.

## Docker

Designed to share the PostgreSQL server and `cl_shared_data` Docker network used by jmcausey/cl.

    cp .env.example .env
    # set OPENWEATHER_API_KEY and matching PostgreSQL credentials
    docker compose up -d --build

Test:

    curl http://localhost:5002/api/v1/health
    curl "http://localhost:5002/api/v1/locations?q=Athens&limit=10"
    curl "http://localhost:5002/api/v1/weather?location=Dallas,%20TX"
    curl "http://localhost:5002/api/v1/history?location=Dallas,%20TX&limit=10"

## Data compatibility

The existing PostgreSQL `chart` and `weather_jobs` tables are retained. The API initializes them if they do not exist, so existing weather history remains available to the new service.

The old HTML templates, static assets, pandas, matplotlib, and UI/control-panel routes are intentionally not part of this repository.

## Examples

curl -i http://localhost:5000/api/v1/health
curl 'http://localhost:5000/api/v1/locations'
curl 'http://localhost:5000/api/v1/locations?q=Dallas&limit=10' 
curl -s 'http://localhost:5000/api/v1/locations?q=Dallas' | python -c 'import json,sys; print(json.load(sys.stdin)["count"])'
curl 'http://localhost:5000/api/v1/locations?q=TX&limit=20'
curl 'http://localhost:5000/api/v1/locations?q=Seattle'
curl 'http://localhost:5000/api/v1/locations?q=Seattle,&WA'
curl 'http://localhost:5000/api/v1/weather?location=Seattle,%20Wa'
curl 'http://localhost:5000/api/v1/weather?latitude=47.6062&longitude=-122.3321'
curl 'http://localhost:5000/api/v1/forecast?latitude=47.6062&longitude=-122.3321'

