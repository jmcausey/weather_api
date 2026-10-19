"""PNG charts from saved PostgreSQL weather observations and forecasts."""
from datetime import timezone
from io import BytesIO

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
from matplotlib.figure import Figure
from flask import Blueprint, current_app, request, send_file, jsonify

from .db import get_db

graphs = Blueprint("graphs", __name__, url_prefix="/api/v1")


@graphs.get("/graphs")
def weather_graph():
    location = (request.args.get("location") or current_app.config.get("CURRENT_LOCATION") or "").strip()
    if not location:
        return jsonify(error="location query parameter is required"), 400
    limit = request.args.get("limit", 500, type=int)
    if not 1 <= limit <= 5000:
        return jsonify(error="limit must be between 1 and 5000"), 400

    db = get_db()
    observations = list(reversed(db.execute(
        """SELECT created_at, temperature, humidity, pressure, windspeed
           FROM chart WHERE location = %s ORDER BY created_at DESC LIMIT %s""",
        (location, limit),
    ).fetchall()))
    forecasts = db.execute(
        """SELECT valid_at, temperature, humidity, pressure, wind_speed, snapshot_at
           FROM weather_forecasts WHERE location = %s
             AND snapshot_at = (SELECT MAX(snapshot_at) FROM weather_forecasts WHERE location = %s)
           ORDER BY valid_at""",
        (location, location),
    ).fetchall()
    if not observations and not forecasts:
        return jsonify(error=f"No saved weather records for {location}"), 404

    fig = Figure(figsize=(12, 10), layout="constrained")
    axes = fig.subplots(4, 1, sharex=True)
    metrics = (
        ("Temperature (°F)", "temperature", "temperature"),
        ("Humidity (%)", "humidity", "humidity"),
        ("Pressure (hPa)", "pressure", "pressure"),
        ("Wind speed (mph)", "windspeed", "wind_speed"),
    )

    def timestamp(value):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    for ax, (ylabel, observed_key, forecast_key) in zip(axes, metrics):
        for rows, field, label, linestyle in (
            (observations, observed_key, "Observed", "-"),
            (forecasts, forecast_key, "Forecast", "--"),
        ):
            pairs = [(timestamp(row["created_at"] if label == "Observed" else row["valid_at"]), row[field])
                     for row in rows if row[field] is not None]
            if pairs:
                ax.plot([t for t, _ in pairs], [v for _, v in pairs],
                        linestyle=linestyle, label=label)
        ax.set_ylabel(ylabel)
        ax.grid(alpha=0.25)
        if ax.lines:
            ax.legend()
    subtitle = (" | latest forecast: " + timestamp(forecasts[0]["snapshot_at"]).strftime("%Y-%m-%d %H:%M UTC")) if forecasts else ""
    fig.suptitle(f"{location} — stored weather history and forecast{subtitle}")
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%b %d %H:%M", tz=timezone.utc))
    axes[-1].set_xlabel("Time (UTC)")
    for tick in axes[-1].get_xticklabels():
        tick.set_rotation(25)
        tick.set_ha("right")
    output = BytesIO()
    fig.savefig(output, format="png", dpi=130)
    output.seek(0)
    response = send_file(output, mimetype="image/png", download_name="weather-graph.png")
    response.headers["Cache-Control"] = "no-store"
    return response
