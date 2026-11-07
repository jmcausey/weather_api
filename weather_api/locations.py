import json
from pathlib import Path


def load_states(db, data_path):
    """Import the bundled state-name and abbreviation dataset into PostgreSQL."""
    data_path = Path(data_path)
    if not data_path.is_file():
        raise FileNotFoundError(f"states dataset not found: {data_path}")

    db.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("weather_api:states",))
    with data_path.open("r", encoding="utf-8") as fh:
        states = json.load(fh)

    rows = [
        (item["name"].strip(), item["abbreviation"].strip().upper())
        for item in states
        if isinstance(item, dict)
        and isinstance(item.get("name"), str)
        and item["name"].strip()
        and isinstance(item.get("abbreviation"), str)
        and item["abbreviation"].strip()
    ]

    with db.cursor() as cur:
        cur.executemany(
            """INSERT INTO states (name, abbreviation)
               VALUES (%s, %s)
               ON CONFLICT (abbreviation) DO UPDATE SET
                   name = EXCLUDED.name""",
            rows,
        )

    return len(rows)


def load_locations(db, data_path):
    """Import locations and normalize city/state/country fields."""
    data_path = Path(data_path)
    if not data_path.is_file():
        raise FileNotFoundError(f"locations dataset not found: {data_path}")

    db.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("weather_api:locations",))
    with data_path.open("r", encoding="utf-8") as fh:
        locations = json.load(fh)

    rows = []
    for display_name, coordinates in locations.items():
        if not isinstance(coordinates, list) or len(coordinates) != 2:
            continue
        latitude, longitude = coordinates
        if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
            continue

        city, separator, region = display_name.rpartition(", ")
        if not separator:
            city, region = display_name, None

        rows.append((display_name, city, region, float(latitude), float(longitude)))

    with db.cursor() as cur:
        cur.executemany(
            """INSERT INTO locations
               (display_name, name, region, city, country, state, latitude, longitude)
               VALUES (
                   %s, %s, %s, %s,
                   CASE WHEN EXISTS (
                       SELECT 1 FROM states s
                       WHERE upper(s.abbreviation) = upper(COALESCE(%s, ''))
                   ) THEN 'United States' ELSE %s END,
                   (SELECT s.name FROM states s
                    WHERE upper(s.abbreviation) = upper(COALESCE(%s, '')) LIMIT 1),
                   %s, %s
               )
               ON CONFLICT (display_name) DO UPDATE SET
                   name = EXCLUDED.name,
                   region = EXCLUDED.region,
                   city = EXCLUDED.city,
                   country = EXCLUDED.country,
                   state = EXCLUDED.state,
                   latitude = EXCLUDED.latitude,
                   longitude = EXCLUDED.longitude""",
            [
                (display_name, city, region, city, region, region, region, latitude, longitude)
                for display_name, city, region, latitude, longitude in rows
            ],
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


def search_locations(query="", limit=50, region=None, country=None, state=None, city=None):
    """Search locations by text and optional hierarchy filters."""
    from .db import get_db

    query = (query or "").strip()
    clauses = []
    params = []

    if query:
        pattern = f"%{query}%"
        clauses.append("""(
            lower(display_name) LIKE lower(%s)
            OR lower(name) LIKE lower(%s)
            OR lower(COALESCE(region, '')) LIKE lower(%s)
            OR lower(COALESCE(country, '')) LIKE lower(%s)
            OR lower(COALESCE(state, '')) LIKE lower(%s)
            OR EXISTS (
                SELECT 1 FROM states s
                WHERE lower(s.name) LIKE lower(%s)
                  AND upper(COALESCE(locations.region, '')) = s.abbreviation
            )
        )""")
        params.extend([pattern] * 6)

    for column, value in (("region", region), ("country", country),
                          ("state", state), ("city", city)):
        if value:
            clauses.append(f"lower(COALESCE({column}, '')) = lower(%s)")
            params.append(value.strip())

    sql = """SELECT display_name, name, region, country, state, city,
                    latitude, longitude
             FROM locations"""
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY country NULLS LAST, state NULLS LAST, city, display_name LIMIT %s"
    params.append(limit)
    return get_db().execute(sql, params).fetchall()
