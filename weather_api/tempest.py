"""Live Tempest station scraping and persistence."""
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

from .db import get_db

FIELDS = {
    "Air Temperature": "temperature_c",
    "Relative Humidity": "humidity_pct",
    "Station Pressure": "pressure_hpa",
    "Wind Speed": "wind_speed_mps",
    "Wind Direction": "wind_direction_deg",
    "Rain Accumulation (Today)": "rainfall_total_mm",
}
DIRECTIONS = {"N": 0, "NNE": 22.5, "NE": 45, "ENE": 67.5, "E": 90,
              "ESE": 112.5, "SE": 135, "SSE": 157.5, "S": 180,
              "SSW": 202.5, "SW": 225, "WSW": 247.5, "W": 270,
              "WNW": 292.5, "NW": 315, "NNW": 337.5}
NUMBER = re.compile(r"[-+]?\d+(?:\.\d+)?")
TIME_FORMATS = ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %I:%M %p")


def parse_reading(label, raw):
    """Normalize displayed units to the sensor-observation schema."""
    raw = raw.strip().replace("−", "-")
    if label == "Wind Direction":
        direction = raw.upper().strip()
        if direction in DIRECTIONS:
            return DIRECTIONS[direction]
        match = NUMBER.search(raw)
        return float(match.group()) % 360 if match else None
    match = NUMBER.search(raw)
    if not match:
        return None
    value = float(match.group())
    lower = raw.lower()
    if label == "Air Temperature":
        if "°f" in lower or "fahrenheit" in lower:
            return (value - 32) * 5 / 9
        if "°c" in lower or "celsius" in lower:
            return value
        return None
    if label == "Station Pressure":
        if "inhg" in lower:
            return value * 33.8638866667
        if "hpa" in lower or "mbar" in lower:
            return value
        return None
    if label == "Wind Speed":
        if "mph" in lower:
            return value * 0.44704
        if "km/h" in lower or "kph" in lower:
            return value / 3.6
        if "m/s" in lower:
            return value
        return None
    if label == "Rain Accumulation (Today)":
        if "mm" in lower:
            return value
        if "in" in lower or '"' in raw:
            return value * 25.4
        return None
    return value


def parse_timestamp(raw, timezone_name):
    if not raw:
        raise ValueError("Tempest page did not expose an observation timestamp")
    raw = raw.strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc)
    except ValueError:
        pass
    if not timezone_name:
        raise ValueError("Tempest page did not expose a timezone")
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(raw, fmt).replace(
                tzinfo=ZoneInfo(timezone_name.strip())
            ).astimezone(timezone.utc)
        except ValueError:
            continue
    raise ValueError("unrecognized Tempest observation timestamp")


def extract_readings(texts):
    """Parse visible label/value elements, including adjacent DOM leaf nodes."""
    cleaned = [re.sub(r"\s+", " ", str(t)).strip() for t in texts]
    cleaned = [t for t in cleaned if t and len(t) < 180]
    labels = set(FIELDS) | {"Timestamp", "Timezone"}
    found = {}
    for i, item in enumerate(cleaned):
        for label in labels:
            if item == label and i + 1 < len(cleaned):
                candidate = cleaned[i + 1]
            elif item.startswith(label + ":"):
                candidate = item[len(label) + 1:].strip()
            elif item.startswith(label + " "):
                candidate = item[len(label):].strip()
            else:
                continue
            if candidate and candidate not in labels and label not in found:
                found[label] = candidate
    measurements = {}
    for label, field in FIELDS.items():
        if label in found:
            parsed = parse_reading(label, found[label])
            if parsed is not None:
                measurements[field] = parsed
    if not measurements:
        raise ValueError("Tempest page contained no recognizable live measurements")
    observed_at = parse_timestamp(found.get("Timestamp"), found.get("Timezone"))
    return {"observed_at": observed_at, **measurements}


def scrape_tempest_station(station_id):
    """Read actual browser-rendered observations, never substitute sample values."""
    station_id = str(station_id).strip()
    if not re.fullmatch(r"\d{1,20}", station_id):
        raise ValueError("station_id must contain 1 to 20 digits")
    url = f"https://tempestwx.com/station/{station_id}"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            response = page.goto(url, wait_until="domcontentloaded", timeout=60000)
            if response is None or response.status >= 400:
                raise RuntimeError("Tempest station page unavailable")
            page.wait_for_function(
                """() => document.body && /Air Temperature|Relative Humidity/.test(document.body.innerText)""",
                timeout=30000,
            )
            texts = page.evaluate("""() => {
                const nodes = document.querySelectorAll('span, div, p, time, label');
                return Array.from(nodes)
                  .filter(el => el.children.length === 0)
                  .map(el => (el.innerText || el.textContent || '').trim())
                  .filter(Boolean);
            }""")
            # Text-node leaves can split labels and values; retain line-based fallback.
            try:
                observation = extract_readings(texts)
            except ValueError:
                observation = extract_readings(page.locator("body").inner_text().splitlines())
            return {"station_id": station_id, **observation}
        finally:
            browser.close()


def collect_tempest_station(station_id):
    observation = scrape_tempest_station(station_id)
    with get_db() as db:
        db.execute(
            """INSERT INTO sensor_stations (station_id, last_seen_at)
               VALUES (%s, CURRENT_TIMESTAMP)
               ON CONFLICT (station_id) DO UPDATE SET last_seen_at=CURRENT_TIMESTAMP""",
            (station_id,),
        )
        row = db.execute(
            """INSERT INTO sensor_observations
               (station_id, observed_at, temperature_c, humidity_pct, pressure_hpa,
                wind_speed_mps, wind_direction_deg, rainfall_total_mm)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (station_id, observed_at) DO UPDATE SET
                 temperature_c=EXCLUDED.temperature_c,
                 humidity_pct=EXCLUDED.humidity_pct,
                 pressure_hpa=EXCLUDED.pressure_hpa,
                 wind_speed_mps=EXCLUDED.wind_speed_mps,
                 wind_direction_deg=EXCLUDED.wind_direction_deg,
                 rainfall_total_mm=EXCLUDED.rainfall_total_mm
               RETURNING id, station_id, observed_at, temperature_c, humidity_pct,
                         pressure_hpa, wind_speed_mps, wind_direction_deg, rainfall_total_mm""",
            (station_id, observation["observed_at"],
             observation.get("temperature_c"), observation.get("humidity_pct"),
             observation.get("pressure_hpa"), observation.get("wind_speed_mps"),
             observation.get("wind_direction_deg"), observation.get("rainfall_total_mm")),
        ).fetchone()
        db.commit()
    return row
