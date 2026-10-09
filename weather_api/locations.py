import json
from pathlib import Path

US_STATE_ABBREVIATIONS = {
    "alabama": "AL",
    "alaska": "AK",
    "arizona": "AZ",
    "arkansas": "AR",
    "california": "CA",
    "colorado": "CO",
    "connecticut": "CT",
    "delaware": "DE",
    "florida": "FL",
    "georgia": "GA",
    "hawaii": "HI",
    "idaho": "ID",
    "illinois": "IL",
    "indiana": "IN",
    "iowa": "IA",
    "kansas": "KS",
    "kentucky": "KY",
    "louisiana": "LA",
    "maine": "ME",
    "maryland": "MD",
    "massachusetts": "MA",
    "michigan": "MI",
    "minnesota": "MN",
    "mississippi": "MS",
    "missouri": "MO",
    "montana": "MT",
    "nebraska": "NE",
    "nevada": "NV",
    "new hampshire": "NH",
    "new jersey": "NJ",
    "new mexico": "NM",
    "new york": "NY",
    "north carolina": "NC",
    "north dakota": "ND",
    "ohio": "OH",
    "oklahoma": "OK",
    "oregon": "OR",
    "pennsylvania": "PA",
    "rhode island": "RI",
    "south carolina": "SC",
    "south dakota": "SD",
    "tennessee": "TN",
    "texas": "TX",
    "utah": "UT",
    "vermont": "VT",
    "virginia": "VA",
    "washington": "WA",
    "west virginia": "WV",
    "wisconsin": "WI",
    "wyoming": "WY",
    "district of columbia": "DC",
}


def load_locations(db, data_path):
    """Import the bundled locations JSON into PostgreSQL once, safely across workers."""
    data_path = Path(data_path)
    if not data_path.is_file():
        raise FileNotFoundError(f"locations dataset not found: {data_path}")

    db.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("weather_api:locations",))
    existing = db.execute("SELECT COUNT(*) AS count FROM locations").fetchone()["count"]
    if existing:
        return existing

    with data_path.open("r", encoding="utf-8") as fh:
        locations = json.load(fh)

    rows = []
    for display_name, coordinates in locations.items():
        if not isinstance(coordinates, list) or len(coordinates) != 2:
            continue
        latitude, longitude = coordinates
        if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
            continue

        name, separator, region = display_name.rpartition(", ")
        if not separator:
            name, region = display_name, None

        rows.append((display_name, name, region, float(latitude), float(longitude)))

    with db.cursor() as cur:
        cur.executemany(
            """INSERT INTO locations
               (display_name, name, region, latitude, longitude)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (display_name) DO UPDATE SET
                   name = EXCLUDED.name,
                   region = EXCLUDED.region,
                   latitude = EXCLUDED.latitude,
                   longitude = EXCLUDED.longitude""",
            rows,
        )

    return len(rows)


def find_location(location):
    """Resolve a location from the local dataset using its canonical display name."""
    if not location:
        return None

    from .db import get_db

    return get_db().execute(
        """SELECT display_name, name, region, latitude, longitude
           FROM locations
           WHERE lower(display_name) = lower(%s)
           LIMIT 1""",
        (location.strip(),),
    ).fetchone()


def search_locations(query, limit=50):
    """Search by display name, city/name, region abbreviation, or full US state name."""
    from .db import get_db

    query = (query or "").strip()
    pattern = f"%{query}%"
    state_abbreviation = US_STATE_ABBREVIATIONS.get(query.casefold())

    return get_db().execute(
        """SELECT display_name, name, region, latitude, longitude
           FROM locations
           WHERE lower(display_name) LIKE lower(%s)
              OR lower(name) LIKE lower(%s)
              OR lower(COALESCE(region, '')) LIKE lower(%s)
              OR (%s IS NOT NULL AND upper(COALESCE(region, '')) = %s)
           ORDER BY name, region, display_name
           LIMIT %s""",
        (
            pattern,
            pattern,
            pattern,
            state_abbreviation,
            state_abbreviation,
            limit,
        ),
    ).fetchall()
