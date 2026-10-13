from datetime import datetime, timezone
import math
import hmac

from flask import Blueprint, current_app, jsonify, request

from .db import get_db
from .locations import search_locations
from .weather import current, forecast, save_current

api = Blueprint("api", __name__, url_prefix="/api/v1")



def utc_iso8601(value):
    """Convert datetime values to ISO 8601 UTC; preserve other JSON values."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, dict):
        return {key: utc_iso8601(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [utc_iso8601(item) for item in value]
    return value


def iso_jsonify(payload):
    """Serialize API response datetimes consistently without changing storage."""
    return jsonify(utc_iso8601(payload))


def error(message, status=400):
    return iso_jsonify({"error": message}), status


def location_args():
    location = request.args.get("location", "").strip() or None
    lat = request.args.get("latitude", type=float)
    lon = request.args.get("longitude", type=float)
    return location, lat, lon


def require_sensor_key():
    configured = str(current_app.config.get("SENSOR_INGEST_API_KEY", "") or "")
    supplied = request.headers.get("X-Sensor-API-Key", "")
    if not configured:
        return error("sensor ingestion is not configured", 503)
    if not supplied or not hmac.compare_digest(supplied, configured):
        return error("invalid or missing sensor API key", 401)
    return None


def optional_number(body, field, minimum=None, maximum=None):
    value = body.get(field)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number or null")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{field} must be finite")
    if minimum is not None and value < minimum:
        raise ValueError(f"{field} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{field} must be at most {maximum}")
    return value


def parse_observed_at(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("observed_at must be an ISO 8601 timestamp with timezone")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("observed_at must be a valid ISO 8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("observed_at must include a timezone, preferably UTC (Z)")
    return parsed.astimezone(timezone.utc)


SENSOR_FIELDS = (
    "temperature_c", "humidity_pct", "pressure_hpa",
    "wind_speed_mps", "wind_direction_deg", "rainfall_mm",
    "rainfall_total_mm",
)


@api.get("/health")
def health():
    try:
        get_db().execute("SELECT 1").fetchone()
        return iso_jsonify({"status": "ok"})
    except Exception:
        return error("database unavailable", 503)


@api.get("/locations")
def locations():
    query = request.args.get("q", "").strip()
    limit = min(max(request.args.get("limit", 50, type=int), 1), 500)
    rows = search_locations(query, limit)
    return iso_jsonify({"count": len(rows), "items": rows})


@api.get("/weather")
def weather():
    location, lat, lon = location_args()
    if not location and (lat is None or lon is None):
        return error("provide location or latitude and longitude")
    try:
        return iso_jsonify(current(location, lat, lon))
    except LookupError as exc:
        return error(str(exc), 404)
    except Exception as exc:
        return error(str(exc), 502)


@api.get("/forecast")
def weather_forecast():
    location, lat, lon = location_args()
    if not location and (lat is None or lon is None):
        return error("provide location or latitude and longitude")
    try:
        return iso_jsonify(forecast(location, lat, lon))
    except LookupError as exc:
        return error(str(exc), 404)
    except Exception as exc:
        return error(str(exc), 502)


@api.post("/weather/collect")
def collect():
    body = request.get_json(silent=True) or {}
    location = body.get("location")
    lat = body.get("latitude")
    lon = body.get("longitude")
    if not location and (lat is None or lon is None):
        return error("provide location or latitude and longitude")
    try:
        payload = current(location, lat, lon)
        save_current(payload)
        return iso_jsonify(payload), 201
    except LookupError as exc:
        return error(str(exc), 404)
    except Exception as exc:
        return error(str(exc), 502)


@api.post("/sensors/observations")
def ingest_sensor_observation():
    auth_error = require_sensor_key()
    if auth_error:
        return auth_error
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return error("request body must be a JSON object")
    station_id = body.get("station_id")
    if not isinstance(station_id, str) or not station_id.strip() or len(station_id.strip()) > 100:
        return error("station_id must be a non-empty string of at most 100 characters")
    station_id = station_id.strip()
    try:
        observed_at = parse_observed_at(body.get("observed_at"))
        values = {
            "temperature_c": optional_number(body, "temperature_c", -80, 85),
            "humidity_pct": optional_number(body, "humidity_pct", 0, 100),
            "pressure_hpa": optional_number(body, "pressure_hpa", 300, 1200),
            "wind_speed_mps": optional_number(body, "wind_speed_mps", 0, 150),
            "wind_direction_deg": optional_number(body, "wind_direction_deg", 0, 359.999),
            "rainfall_mm": optional_number(body, "rainfall_mm", 0, 1000),
            "rainfall_total_mm": optional_number(body, "rainfall_total_mm", 0, None),
        }
    except ValueError as exc:
        return error(str(exc))
    if all(value is None for value in values.values()):
        return error("at least one sensor measurement must be supplied")

    sql_values = [values[field] for field in SENSOR_FIELDS]
    with get_db() as db:
        db.execute(
            """INSERT INTO sensor_stations (station_id, last_seen_at)
               VALUES (%s, CURRENT_TIMESTAMP)
               ON CONFLICT (station_id) DO UPDATE SET last_seen_at = CURRENT_TIMESTAMP""",
            (station_id,),
        )
        row = db.execute(
            """INSERT INTO sensor_observations
               (station_id, observed_at, temperature_c, humidity_pct, pressure_hpa,
                wind_speed_mps, wind_direction_deg, rainfall_mm, rainfall_total_mm)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING id, station_id, observed_at, received_at, temperature_c,
                         humidity_pct, pressure_hpa, wind_speed_mps,
                         wind_direction_deg, rainfall_mm, rainfall_total_mm""",
            (station_id, observed_at, *sql_values),
        ).fetchone()
        db.commit()
    return iso_jsonify({"status": "accepted", "observation": row}), 201


@api.get("/sensors/<station_id>/latest")
def latest_sensor_observation(station_id):
    row = get_db().execute(
        """SELECT id, station_id, observed_at, received_at, temperature_c, humidity_pct,
                  pressure_hpa, wind_speed_mps, wind_direction_deg, rainfall_mm,
                  rainfall_total_mm
           FROM sensor_observations WHERE station_id=%s
           ORDER BY observed_at DESC, id DESC LIMIT 1""",
        (station_id,),
    ).fetchone()
    if not row:
        return error("no observations found for station", 404)
    return iso_jsonify(row)


@api.get("/sensors/<station_id>/history")
def sensor_observation_history(station_id):
    limit = min(max(request.args.get("limit", 50, type=int), 1), 1000)
    rows = get_db().execute(
        """SELECT id, station_id, observed_at, received_at, temperature_c, humidity_pct,
                  pressure_hpa, wind_speed_mps, wind_direction_deg, rainfall_mm,
                  rainfall_total_mm
           FROM sensor_observations WHERE station_id=%s
           ORDER BY observed_at DESC, id DESC LIMIT %s""",
        (station_id, limit),
    ).fetchall()
    return iso_jsonify({"station_id": station_id, "count": len(rows), "items": rows})


@api.get("/history")
def history():
    location = request.args.get("location", "").strip()
    limit = min(max(request.args.get("limit", 50, type=int), 1), 500)
    query = """SELECT id, created_at, location, geolocation, description, temperature,
                      pressure, feelslike AS feels_like, humidity, visibility,
                      windspeed AS wind_speed, winddirection AS wind_direction,
                      clouds, sunrise, sunset, dew_point FROM chart"""
    params = []
    if location:
        query += " WHERE location = %s"
        params.append(location)
    query += " ORDER BY created_at DESC LIMIT %s"
    params.append(limit)
    rows = get_db().execute(query, params).fetchall()
    return iso_jsonify({"count": len(rows), "items": rows})


@api.get("/forecasts")
def stored_forecasts():
    location = request.args.get("location", "").strip()
    limit = min(max(request.args.get("limit", 100, type=int), 1), 1000)
    query = """SELECT id, location, provider, snapshot_at, valid_at, temperature,
                      feels_like, pressure, description, precipitation_probability,
                      precipitation_amount, humidity, wind_speed, wind_direction, clouds
               FROM weather_forecasts"""
    params = []
    if location:
        query += " WHERE location = %s"
        params.append(location)
    query += " ORDER BY snapshot_at DESC, valid_at ASC LIMIT %s"
    params.append(limit)
    rows = get_db().execute(query, params).fetchall()
    return iso_jsonify({"count": len(rows), "items": rows})


@api.get("/jobs")
def jobs():
    rows = get_db().execute("SELECT * FROM weather_jobs ORDER BY enabled DESC, name").fetchall()
    return iso_jsonify({"count": len(rows), "items": rows})


@api.post("/jobs")
def create_job():
    body = request.get_json(silent=True) or {}
    required = ("name", "location", "latitude", "longitude", "interval_minutes")
    missing = [field for field in required if body.get(field) is None]
    if missing:
        return error("missing fields: " + ", ".join(missing))
    job_type = str(body.get("job_type", "current")).strip().lower()
    if job_type not in ("current", "forecast"):
        return error("job_type must be 'current' or 'forecast'")
    if body["interval_minutes"] not in (15, 60, 240, 1440):
        return error("interval_minutes must be 15, 60, 240, or 1440")
    try:
        with get_db() as db:
            row = db.execute(
                """INSERT INTO weather_jobs
                   (name, location, latitude, longitude, interval_minutes, enabled, job_type)
                   VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                (body["name"], body["location"], float(body["latitude"]),
                 float(body["longitude"]), body["interval_minutes"],
                 bool(body.get("enabled", True)), job_type),
            ).fetchone()
            db.commit()
        return iso_jsonify(row), 201
    except (TypeError, ValueError):
        return error("latitude and longitude must be numbers")


@api.delete("/jobs/<int:job_id>")
def delete_job(job_id):
    with get_db() as db:
        result = db.execute("DELETE FROM weather_jobs WHERE id=%s", (job_id,))
        db.commit()
    if result.rowcount == 0:
        return error("job not found", 404)
    return iso_jsonify({"deleted": job_id})


@api.post("/jobs/<int:job_id>/run")
def run_job(job_id):
    from .tasks import run_weather_job
    if not run_weather_job(job_id):
        return error("job failed; inspect weather_jobs.last_error", 502)
    return iso_jsonify({"id": job_id, "status": "completed"})


@api.get("/tempest/stations")
def tempest_stations():
    rows = get_db().execute("SELECT * FROM tempest_jobs ORDER BY name").fetchall()
    return iso_jsonify({"count": len(rows), "items": rows})


@api.post("/tempest/stations")
def register_tempest_station():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return error("request body must be a JSON object")
    import re
    station_id = str(body.get("station_id", "")).strip()
    if not re.fullmatch(r"\d{1,20}", station_id):
        return error("station_id must contain 1 to 20 digits")
    name = body.get("name", f"Tempest {station_id}")
    interval = body.get("interval_minutes", 15)
    if not isinstance(name, str) or not name.strip() or len(name) > 120:
        return error("name must be a non-empty string of at most 120 characters")
    if type(interval) is not int or interval not in (15, 60, 240, 1440):
        return error("interval_minutes must be 15, 60, 240, or 1440")
    if type(body.get("enabled", True)) is not bool:
        return error("enabled must be boolean")
    with get_db() as db:
        row = db.execute(
            """INSERT INTO tempest_jobs (station_id,name,interval_minutes,enabled)
               VALUES (%s,%s,%s,%s)
               ON CONFLICT (station_id) DO UPDATE SET
                 name=EXCLUDED.name,interval_minutes=EXCLUDED.interval_minutes,
                 enabled=EXCLUDED.enabled,updated_at=CURRENT_TIMESTAMP
               RETURNING *""",
            (station_id, name.strip(), interval, body.get("enabled", True)),
        ).fetchone()
        db.commit()
    return iso_jsonify(row), 201


@api.delete("/tempest/stations/<station_id>")
def remove_tempest_station(station_id):
    with get_db() as db:
        result = db.execute("DELETE FROM tempest_jobs WHERE station_id=%s", (station_id,))
        db.commit()
    if result.rowcount == 0:
        return error("station job not found", 404)
    return iso_jsonify({"deleted": station_id})


@api.post("/tempest/stations/<station_id>/run")
def collect_tempest_now(station_id):
    """Queue collection for the scheduler; never run Chromium in Gunicorn."""
    with get_db() as db:
        row = db.execute(
            """UPDATE tempest_jobs SET last_status='queued',
               updated_at=CURRENT_TIMESTAMP WHERE station_id=%s AND enabled=TRUE
               RETURNING station_id""",
            (station_id,),
        ).fetchone()
        db.commit()
    if not row:
        return error("enabled station job not found", 404)
    return iso_jsonify({"station_id": station_id, "status": "queued"}), 202
