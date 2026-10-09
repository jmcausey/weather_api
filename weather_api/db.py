from pathlib import Path

import psycopg
from flask import current_app, g
from psycopg.rows import dict_row

from .locations import load_locations, load_states


def get_db():
    if "db" not in g:
        g.db = psycopg.connect(current_app.config["DATABASE_URL"], row_factory=dict_row)
    return g.db


def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(app):
    app.teardown_appcontext(close_db)
    with app.app_context():
        db = get_db()
        db.execute("""CREATE TABLE IF NOT EXISTS chart (
            id BIGSERIAL PRIMARY KEY, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            location TEXT NOT NULL, geolocation TEXT, description TEXT,
            temperature DOUBLE PRECISION, pressure INTEGER, feelslike DOUBLE PRECISION,
            humidity INTEGER, visibility INTEGER, windspeed DOUBLE PRECISION,
            winddirection INTEGER, clouds INTEGER, sunrise TIMESTAMP, sunset TIMESTAMP,
            dew_point DOUBLE PRECISION)""")
        db.execute("CREATE INDEX IF NOT EXISTS idx_chart_location_created ON chart(location, created_at DESC)")
        db.execute("""CREATE TABLE IF NOT EXISTS weather_jobs (
            id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, location TEXT NOT NULL,
            latitude DOUBLE PRECISION NOT NULL, longitude DOUBLE PRECISION NOT NULL,
            interval_minutes INTEGER NOT NULL CHECK (interval_minutes IN (15,60,240,1440)),
            enabled BOOLEAN NOT NULL DEFAULT TRUE, last_run_at TIMESTAMP,
            last_status TEXT, last_error TEXT, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        # Add the column to existing installations without deleting their jobs.
        db.execute("ALTER TABLE weather_jobs ADD COLUMN IF NOT EXISTS job_type TEXT NOT NULL DEFAULT 'current'")
        db.execute("CREATE INDEX IF NOT EXISTS idx_weather_jobs_enabled_run ON weather_jobs(enabled, last_run_at)")
        db.execute("""CREATE TABLE IF NOT EXISTS weather_forecasts (
            id BIGSERIAL PRIMARY KEY,
            location TEXT NOT NULL,
            provider TEXT NOT NULL,
            snapshot_at TIMESTAMPTZ NOT NULL,
            valid_at TIMESTAMPTZ NOT NULL,
            temperature DOUBLE PRECISION,
            feels_like DOUBLE PRECISION,
            pressure INTEGER,
            description TEXT,
            precipitation_probability DOUBLE PRECISION,
            precipitation_amount DOUBLE PRECISION,
            humidity INTEGER,
            wind_speed DOUBLE PRECISION,
            wind_direction INTEGER,
            clouds INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (location, provider, snapshot_at, valid_at)
        )""")
        db.execute("CREATE INDEX IF NOT EXISTS idx_weather_forecasts_location_valid ON weather_forecasts(location, valid_at)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_weather_forecasts_location_snapshot ON weather_forecasts(location, snapshot_at DESC)")
        db.execute("""CREATE TABLE IF NOT EXISTS states (
            name TEXT NOT NULL,
            abbreviation TEXT PRIMARY KEY
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS locations (
            display_name TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            region TEXT,
            latitude DOUBLE PRECISION NOT NULL,
            longitude DOUBLE PRECISION NOT NULL
        )""")
        db.execute("CREATE INDEX IF NOT EXISTS idx_locations_name ON locations(name)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_locations_region ON locations(region)")
        data_dir = Path(app.root_path).parent / "data" / "locations"
        load_states(db, data_dir / "states.json")
        load_locations(db, data_dir / "locations.json")
        db.commit()
