import math
import os
from datetime import datetime, timedelta, timezone

import requests

from .db import get_db
from .locations import find_location


def _key():
    return os.environ.get("OPENWEATHER_API_KEY")


def geocode(location):
    if not location:
        return None
    local = find_location(location)
    if local:
        return {"name": local["name"], "region": local["region"],
                "latitude": local["latitude"], "longitude": local["longitude"]}
    if not _key():
        return None
    response = requests.get(
        "https://api.openweathermap.org/geo/1.0/direct",
        params={"q": location, "limit": 1, "appid": _key()}, timeout=10,
    )
    response.raise_for_status()
    items = response.json()
    if not items:
        return None
    item = items[0]
    return {"name": item.get("name") or location, "country": item.get("country"),
            "state": item.get("state"), "latitude": item["lat"], "longitude": item["lon"]}


def current_by_coordinates(latitude, longitude):
    if not _key():
        raise RuntimeError("OPENWEATHER_API_KEY is not configured")
    response = requests.get(
        "https://api.openweathermap.org/data/2.5/weather",
        params={"lat": latitude, "lon": longitude, "appid": _key(), "units": "imperial"},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def normalize_current(payload, requested_location=None):
    coord = payload.get("coord", {})
    weather = (payload.get("weather") or [{}])[0]
    main = payload.get("main", {})
    wind = payload.get("wind", {})
    system = payload.get("sys", {})
    temp = main.get("temp")
    humidity = main.get("humidity")
    dew = None
    if temp is not None and humidity:
        vapor = math.log(humidity / 100) + (17.27 * temp) / (temp + 237.3)
        dew = round((237.3 * vapor) / (17.27 - vapor))

    def iso(value):
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat() if value else None

    return {
        "location": requested_location or payload.get("name"),
        "observed_location": payload.get("name"),
        "country": system.get("country"),
        "latitude": coord.get("lat"), "longitude": coord.get("lon"),
        "description": weather.get("description"), "temperature": temp,
        "feels_like": main.get("feels_like"), "pressure": main.get("pressure"),
        "humidity": humidity, "visibility": payload.get("visibility"),
        "wind_speed": wind.get("speed"), "wind_direction": wind.get("deg"),
        "clouds": (payload.get("clouds") or {}).get("all"),
        "sunrise": iso(system.get("sunrise")), "sunset": iso(system.get("sunset")),
        "dew_point": dew,
    }


def current(location=None, latitude=None, longitude=None):
    if latitude is None or longitude is None:
        resolved = geocode(location)
        if not resolved:
            raise LookupError(f"Location not found: {location}")
        latitude, longitude = resolved["latitude"], resolved["longitude"]
    return normalize_current(current_by_coordinates(latitude, longitude), location)


def forecast(location=None, latitude=None, longitude=None):
    if latitude is None or longitude is None:
        resolved = geocode(location)
        if not resolved:
            raise LookupError(f"Location not found: {location}")
        latitude, longitude = resolved["latitude"], resolved["longitude"]
        location = location or resolved["name"]
    if not _key():
        raise RuntimeError("OPENWEATHER_API_KEY is not configured")

    response = requests.get(
        "https://api.openweathermap.org/data/2.5/forecast",
        params={"lat": latitude, "lon": longitude, "appid": _key(), "units": "imperial"},
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    city = payload.get("city") or {}
    points = []
    local_timezone = timezone(timedelta(seconds=city.get("timezone", 0)))

    for item in payload.get("list", []):
        weather = (item.get("weather") or [{}])[0]
        main = item.get("main") or {}
        wind = item.get("wind") or {}
        valid_at = datetime.fromtimestamp(item["dt"], tz=timezone.utc)
        rain = (item.get("rain") or {}).get("3h")
        snow = (item.get("snow") or {}).get("3h")
        precipitation_amount = ((rain or 0) + (snow or 0)) if rain is not None or snow is not None else None
        points.append({
            "time": valid_at.astimezone(local_timezone).isoformat(),
            "valid_at": valid_at.isoformat(),
            "temperature": main.get("temp"),
            "feels_like": main.get("feels_like"),
            "pressure": main.get("pressure"),
            "description": weather.get("description"),
            "icon": weather.get("icon"),
            "precipitation_probability": round((item.get("pop") or 0) * 100),
            "precipitation_amount": precipitation_amount,
            "humidity": main.get("humidity"),
            "wind_speed": wind.get("speed"),
            "wind_direction": wind.get("deg"),
            "clouds": (item.get("clouds") or {}).get("all"),
        })
    return {"provider": "openweathermap", "location": location or city.get("name"),
            "city": city.get("name"), "country": city.get("country"),
            "latitude": latitude, "longitude": longitude, "points": points}


def save_current(payload):
    with get_db() as db:
        db.execute(
            """INSERT INTO chart
               (location, geolocation, description, temperature, pressure, feelslike, humidity,
                visibility, windspeed, winddirection, clouds, sunrise, sunset, dew_point)
               VALUES (%(location)s, %(geolocation)s, %(description)s, %(temperature)s, %(pressure)s,
                       %(feelslike)s, %(humidity)s, %(visibility)s, %(windspeed)s, %(winddirection)s,
                       %(clouds)s, %(sunrise)s, %(sunset)s, %(dew_point)s)""",
            {"location": payload["location"],
             "geolocation": f'{payload["latitude"]},{payload["longitude"]}',
             "description": payload["description"], "temperature": payload["temperature"],
             "pressure": payload["pressure"], "feelslike": payload["feels_like"],
             "humidity": payload["humidity"], "visibility": payload["visibility"],
             "windspeed": payload["wind_speed"], "winddirection": payload["wind_direction"],
             "clouds": payload["clouds"], "sunrise": payload["sunrise"],
             "sunset": payload["sunset"], "dew_point": payload["dew_point"]},
        )
        db.commit()


def save_forecast(payload):
    """Persist each forecast period as part of a timestamped forecast snapshot."""
    snapshot_at = datetime.now(timezone.utc)
    points = payload.get("points", [])
    if not points:
        raise ValueError("forecast provider returned no forecast points")
    rows = [
        (payload["location"], payload.get("provider", "openweathermap"), snapshot_at,
         point["valid_at"], point.get("temperature"), point.get("feels_like"),
         point.get("pressure"), point.get("description"),
         point.get("precipitation_probability"), point.get("precipitation_amount"),
         point.get("humidity"), point.get("wind_speed"), point.get("wind_direction"),
         point.get("clouds"))
        for point in points
    ]
    with get_db() as db:
        with db.cursor() as cur:
            cur.executemany(
                """INSERT INTO weather_forecasts
                   (location, provider, snapshot_at, valid_at, temperature, feels_like,
                    pressure, description, precipitation_probability, precipitation_amount,
                    humidity, wind_speed, wind_direction, clouds)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (location, provider, snapshot_at, valid_at) DO NOTHING""",
                rows,
            )
        db.commit()
    return len(rows)
