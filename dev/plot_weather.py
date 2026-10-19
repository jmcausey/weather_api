"""Plot saved current weather and the latest forecast snapshot from PostgreSQL.

Run: python dev/plot_weather.py --location "Malakoff, TX" --output weather.png
Requires: matplotlib, psycopg[binary]; PostgreSQL environment variables or DATABASE_URL.
"""
import argparse
import os
from datetime import datetime, timezone
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import psycopg


def utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--location", required=True)
    parser.add_argument("--output", default="weather.png")
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()
    if not 1 <= args.limit <= 10000:
        parser.error("--limit must be between 1 and 10000")

    dsn = os.getenv("DATABASE_URL")
    connection_args = {"conninfo": dsn} if dsn else {
        "host": os.getenv("PGHOST", "localhost"),
        "port": int(os.getenv("PGPORT", "5432")),
        "dbname": os.getenv("PGDATABASE", "cl"),
        "user": os.getenv("PGUSER", "cl"),
        "password": os.getenv("PGPASSWORD", ""),
    }
    with psycopg.connect(**connection_args) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT created_at, temperature, humidity, pressure, windspeed
                   FROM chart WHERE location = %s
                   ORDER BY created_at DESC LIMIT %s""",
                (args.location, args.limit),
            )
            observed = list(reversed(cur.fetchall()))
            cur.execute(
                """SELECT valid_at, temperature, humidity, pressure, wind_speed,
                          precipitation_probability, snapshot_at
                   FROM weather_forecasts
                   WHERE location = %s
                     AND snapshot_at = (
                       SELECT MAX(snapshot_at) FROM weather_forecasts WHERE location = %s
                     )
                   ORDER BY valid_at""",
                (args.location, args.location),
            )
            predicted = cur.fetchall()

    if not observed and not predicted:
        parser.error(f"No stored observations or forecasts for {args.location!r}")

    metrics = [
        ("Temperature", "°F", 1, 1),
        ("Humidity", "%", 2, 2),
        ("Pressure", "hPa", 3, 3),
        ("Wind speed", "mph", 4, 4),
    ]
    fig, axes = plt.subplots(4, 1, figsize=(13, 11), sharex=True, constrained_layout=True)
    for ax, (title, units, history_col, forecast_col) in zip(axes, metrics):
        for rows, col, label, style in (
            (observed, history_col, "Observed", "-"),
            (predicted, forecast_col, "Latest forecast", "--"),
        ):
            pairs = [(utc(r[0]), r[col]) for r in rows if r[col] is not None]
            if pairs:
                ax.plot([p[0] for p in pairs], [p[1] for p in pairs],
                        linestyle=style, marker="." if style == "-" else None,
                        label=label)
        ax.set_ylabel(f"{title} ({units})")
        ax.grid(alpha=0.25)
        if ax.lines:
            ax.legend(loc="best")

    if predicted:
        snapshot = utc(predicted[0][6]).strftime("%Y-%m-%d %H:%M UTC")
        subtitle = f" | forecast collected {snapshot}"
    else:
        subtitle = " | no stored forecast"
    fig.suptitle(f"{args.location} — historical weather and forecast{subtitle}")
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%b %d %H:%M", tz=timezone.utc))
    axes[-1].set_xlabel("Time (UTC)")
    plt.setp(axes[-1].get_xticklabels(), rotation=25, ha="right")
    fig.savefig(args.output, dpi=160)
    plt.close(fig)
    print(f"Saved {args.output} ({len(observed)} observations, {len(predicted)} forecast periods)")


if __name__ == "__main__":
    main()
