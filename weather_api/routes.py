from flask import Blueprint, jsonify, request

from .db import get_db
from .weather import current, forecast, save_current

api = Blueprint("api", __name__, url_prefix="/api/v1")


def error(message, status=400):
    return jsonify({"error": message}), status


def location_args():
    location = request.args.get("location", "").strip() or None
    lat = request.args.get("latitude", type=float)
    lon = request.args.get("longitude", type=float)
    return location, lat, lon


@api.get("/health")
def health():
    try:
        get_db().execute("SELECT 1").fetchone()
        return jsonify({"status": "ok"})
    except Exception:
        return error("database unavailable", 503)


@api.get("/weather")
def weather():
    location, lat, lon = location_args()
    if not location and (lat is None or lon is None):
        return error("provide location or latitude and longitude")
    try:
        return jsonify(current(location, lat, lon))
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
        return jsonify(forecast(location, lat, lon))
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
        return jsonify(payload), 201
    except LookupError as exc:
        return error(str(exc), 404)
    except Exception as exc:
        return error(str(exc), 502)


@api.get("/history")
def history():
    location = request.args.get("location", "").strip()
    limit = min(max(request.args.get("limit", 50, type=int), 1), 500)
    query = """SELECT id, created_at, location, geolocation, description, temperature,
                      pressure, feelslike AS feels_like, humidity, visibility,
                      windspeed AS wind_speed, winddirection AS wind_direction,
                      clouds, sunrise, sunset, dew_point
               FROM chart"""
    params = []
    if location:
        query += " WHERE location = %s"
        params.append(location)
    query += " ORDER BY created_at DESC LIMIT %s"
    params.append(limit)
    rows = get_db().execute(query, params).fetchall()
    return jsonify({"count": len(rows), "items": rows})


@api.get("/jobs")
def jobs():
    rows = get_db().execute("SELECT * FROM weather_jobs ORDER BY enabled DESC, name").fetchall()
    return jsonify({"count": len(rows), "items": rows})


@api.post("/jobs")
def create_job():
    body = request.get_json(silent=True) or {}
    required = ("name", "location", "latitude", "longitude", "interval_minutes")
    missing = [field for field in required if body.get(field) is None]
    if missing:
        return error("missing fields: " + ", ".join(missing))
    if body["interval_minutes"] not in (15, 60, 240, 1440):
        return error("interval_minutes must be 15, 60, 240, or 1440")
    try:
        with get_db() as db:
            row = db.execute(
                """INSERT INTO weather_jobs
                   (name, location, latitude, longitude, interval_minutes, enabled)
                   VALUES (%s,%s,%s,%s,%s,%s) RETURNING *""",
                (body["name"], body["location"], float(body["latitude"]),
                 float(body["longitude"]), body["interval_minutes"],
                 bool(body.get("enabled", True))),
            ).fetchone()
            db.commit()
        return jsonify(row), 201
    except (TypeError, ValueError):
        return error("latitude and longitude must be numbers")


@api.delete("/jobs/<int:job_id>")
def delete_job(job_id):
    with get_db() as db:
        result = db.execute("DELETE FROM weather_jobs WHERE id=%s", (job_id,))
        db.commit()
    if result.rowcount == 0:
        return error("job not found", 404)
    return jsonify({"deleted": job_id})


@api.post("/jobs/<int:job_id>/run")
def run_job(job_id):
    from .tasks import run_weather_job
    if not run_weather_job(job_id):
        return error("job failed; inspect weather_jobs.last_error", 502)
    return jsonify({"id": job_id, "status": "completed"})
