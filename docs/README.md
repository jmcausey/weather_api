# Weather API Documentation

This directory documents the `weather_api` application, its HTTP API, database schema, background scheduler, installation, and deployment.

## Guides

- [Interactive installer](installer.md) — guided OpenWeatherMap setup, environment prompts, and Docker startup.
- [Architecture and code map](architecture.md) — application startup, modules, and request/data flow.
- [HTTP API reference](api-reference.md) — endpoints, parameters, request bodies, and examples.
- [Database schema](database.md) — tables, columns, indexes, and retention behavior.
- [Configuration and deployment](configuration.md) — environment variables, Docker Compose, startup, and troubleshooting.

## Service overview

The service is a Flask JSON API backed by PostgreSQL. It uses OpenWeatherMap for current conditions and forecast data. A separate scheduler container runs enabled collection jobs on their configured intervals.

Bundled location and state datasets are stored under `data/locations/` and imported into PostgreSQL at application startup. Location lookup uses the local dataset first; OpenWeatherMap geocoding is used as a fallback when a local match is unavailable and an API key is configured.

## Quick links

- [Project README](../README.md)
- [Installer script](../install.sh)
- [Source package](../weather_api/)
- [Docker Compose configuration](../docker-compose.yml)
