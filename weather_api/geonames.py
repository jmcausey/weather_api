"""PostgreSQL storage and import helpers for the normalized GeoNames database."""
from pathlib import Path
import sqlite3

CONTINENTS = {
    "AF": "Africa", "AS": "Asia", "EU": "Europe", "NA": "North America",
    "OC": "Oceania", "SA": "South America", "AN": "Antarctica",
}


def ensure_geonames_schema(db):
    """Create normalized GeoNames tables without changing legacy locations."""
    statements = (
        """CREATE TABLE IF NOT EXISTS geo_countries (
            iso2 TEXT PRIMARY KEY, iso3 TEXT, iso_numeric TEXT, fips_code TEXT,
            name TEXT NOT NULL, capital TEXT, continent_code TEXT, languages TEXT,
            population BIGINT, area_sq_km DOUBLE PRECISION, currency_code TEXT,
            tld TEXT, neighbours TEXT, geoname_id BIGINT
        )""",
        """CREATE TABLE IF NOT EXISTS geo_admin1 (
            country_iso2 TEXT NOT NULL REFERENCES geo_countries(iso2),
            admin1_code TEXT NOT NULL, name TEXT NOT NULL, ascii_name TEXT,
            geoname_id BIGINT, PRIMARY KEY (country_iso2, admin1_code)
        )""",
        """CREATE TABLE IF NOT EXISTS geo_admin2 (
            country_iso2 TEXT NOT NULL, admin1_code TEXT NOT NULL,
            admin2_code TEXT NOT NULL, name TEXT NOT NULL, ascii_name TEXT,
            geoname_id BIGINT,
            PRIMARY KEY (country_iso2, admin1_code, admin2_code),
            FOREIGN KEY (country_iso2, admin1_code)
                REFERENCES geo_admin1(country_iso2, admin1_code)
        )""",
        """CREATE TABLE IF NOT EXISTS geo_places (
            geoname_id BIGINT PRIMARY KEY, name TEXT NOT NULL, ascii_name TEXT,
            latitude DOUBLE PRECISION NOT NULL, longitude DOUBLE PRECISION NOT NULL,
            feature_code TEXT, country_iso2 TEXT NOT NULL REFERENCES geo_countries(iso2),
            admin1_code TEXT, admin2_code TEXT, admin3_code TEXT, admin4_code TEXT,
            population BIGINT NOT NULL DEFAULT 0, elevation_m INTEGER, dem_m INTEGER,
            timezone TEXT, modified_date DATE
        )""",
        "CREATE INDEX IF NOT EXISTS idx_geo_places_name ON geo_places (lower(name))",
        "CREATE INDEX IF NOT EXISTS idx_geo_places_country_admin ON geo_places (country_iso2, admin1_code, admin2_code)",
        "CREATE INDEX IF NOT EXISTS idx_geo_places_population ON geo_places (population DESC)",
        "CREATE INDEX IF NOT EXISTS idx_geo_admin1_name ON geo_admin1 (lower(name))",
        "CREATE INDEX IF NOT EXISTS idx_geo_admin2_name ON geo_admin2 (lower(name))",
    )
    for statement in statements:
        db.execute(statement)


def _copy_table(source, target, select_sql, insert_sql, batch_size=5000):
    source_cursor = source.execute(select_sql)
    total = 0
    while True:
        rows = source_cursor.fetchmany(batch_size)
        if not rows:
            break
        with target.cursor() as target_cursor:
            target_cursor.executemany(insert_sql, rows)
        total += len(rows)
    return total


def import_geonames_sqlite(db, sqlite_path, batch_size=5000):
    """Upsert a built locations.sqlite3 snapshot into PostgreSQL.

    Existing weather_api locations and weather history are never deleted or
    rewritten. Re-importing the same GeoNames snapshot is safe.
    """
    path = Path(sqlite_path)
    if not path.is_file():
        raise FileNotFoundError(f"GeoNames SQLite database not found: {path}")
    source = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    source.row_factory = None
    counts = {}
    try:
        ensure_geonames_schema(db)
        counts["countries"] = _copy_table(
            source, db,
            "SELECT iso2,iso3,iso_numeric,fips_code,name,capital,continent_code,languages,population,area_sq_km,currency_code,tld,neighbours,geoname_id FROM countries",
            """INSERT INTO geo_countries VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (iso2) DO UPDATE SET iso3=EXCLUDED.iso3,
               iso_numeric=EXCLUDED.iso_numeric, fips_code=EXCLUDED.fips_code,
               name=EXCLUDED.name, capital=EXCLUDED.capital,
               continent_code=EXCLUDED.continent_code, languages=EXCLUDED.languages,
               population=EXCLUDED.population, area_sq_km=EXCLUDED.area_sq_km,
               currency_code=EXCLUDED.currency_code, tld=EXCLUDED.tld,
               neighbours=EXCLUDED.neighbours, geoname_id=EXCLUDED.geoname_id""",
            batch_size,
        )
        counts["admin1"] = _copy_table(
            source, db,
            "SELECT country_iso2,admin1_code,name,ascii_name,geoname_id FROM admin1",
            """INSERT INTO geo_admin1 VALUES (%s,%s,%s,%s,%s)
               ON CONFLICT (country_iso2,admin1_code) DO UPDATE SET
               name=EXCLUDED.name, ascii_name=EXCLUDED.ascii_name,
               geoname_id=EXCLUDED.geoname_id""",
            batch_size,
        )
        counts["admin2"] = _copy_table(
            source, db,
            "SELECT country_iso2,admin1_code,admin2_code,name,ascii_name,geoname_id FROM admin2",
            """INSERT INTO geo_admin2 VALUES (%s,%s,%s,%s,%s,%s)
               ON CONFLICT (country_iso2,admin1_code,admin2_code) DO UPDATE SET
               name=EXCLUDED.name, ascii_name=EXCLUDED.ascii_name,
               geoname_id=EXCLUDED.geoname_id""",
            batch_size,
        )
        counts["places"] = _copy_table(
            source, db,
            """SELECT geoname_id,name,ascii_name,latitude,longitude,feature_code,
                      country_iso2,admin1_code,admin2_code,admin3_code,admin4_code,
                      population,elevation_m,dem_m,timezone,modified_date FROM places""",
            """INSERT INTO geo_places VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (geoname_id) DO UPDATE SET name=EXCLUDED.name,
               ascii_name=EXCLUDED.ascii_name, latitude=EXCLUDED.latitude,
               longitude=EXCLUDED.longitude, feature_code=EXCLUDED.feature_code,
               country_iso2=EXCLUDED.country_iso2, admin1_code=EXCLUDED.admin1_code,
               admin2_code=EXCLUDED.admin2_code, admin3_code=EXCLUDED.admin3_code,
               admin4_code=EXCLUDED.admin4_code, population=EXCLUDED.population,
               elevation_m=EXCLUDED.elevation_m, dem_m=EXCLUDED.dem_m,
               timezone=EXCLUDED.timezone, modified_date=EXCLUDED.modified_date""",
            batch_size,
        )
        db.commit()
        return counts
    except Exception:
        db.rollback()
        raise
    finally:
        source.close()


def search_geonames(db, *, query="", continent=None, country=None, country_code=None,
                    state=None, county=None, city=None, limit=50, offset=0):
    """Return a stable, paginated GeoNames hierarchy result and total."""
    clauses = []
    params = []
    if continent:
        clauses.append("""CASE c.continent_code
            WHEN 'AF' THEN 'Africa' WHEN 'AS' THEN 'Asia' WHEN 'EU' THEN 'Europe'
            WHEN 'NA' THEN 'North America' WHEN 'OC' THEN 'Oceania'
            WHEN 'SA' THEN 'South America' WHEN 'AN' THEN 'Antarctica'
            ELSE NULL END ILIKE %s""")
        params.append(continent.strip())
    if country:
        clauses.append("c.name ILIKE %s")
        params.append(country.strip())
    if country_code:
        clauses.append("(c.iso2 ILIKE %s OR c.iso3 ILIKE %s OR c.iso_numeric = %s)")
        params.extend([country_code.strip(), country_code.strip(), country_code.strip()])
    if state:
        clauses.append("a1.name ILIKE %s")
        params.append(state.strip())
    if county:
        clauses.append("a2.name ILIKE %s")
        params.append(county.strip())
    if city:
        clauses.append("p.name ILIKE %s")
        params.append(city.strip())
    if query:
        pattern = f"%{query.strip()}%"
        clauses.append("""(p.name ILIKE %s OR p.ascii_name ILIKE %s OR
            c.name ILIKE %s OR a1.name ILIKE %s OR a2.name ILIKE %s OR
            p.geoname_id::text = %s)""")
        params.extend([pattern] * 5 + [query.strip()])
    joins = """ FROM geo_places p
        JOIN geo_countries c ON c.iso2=p.country_iso2
        LEFT JOIN geo_admin1 a1 ON a1.country_iso2=p.country_iso2
            AND a1.admin1_code=p.admin1_code
        LEFT JOIN geo_admin2 a2 ON a2.country_iso2=p.country_iso2
            AND a2.admin1_code=p.admin1_code AND a2.admin2_code=p.admin2_code"""
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    total = db.execute("SELECT COUNT(*) AS total" + joins + where, params).fetchone()["total"]
    select = """SELECT p.geoname_id, p.name AS city, p.ascii_name,
        p.latitude, p.longitude, p.feature_code, p.population, p.elevation_m,
        p.timezone, p.modified_date, c.iso2 AS country_code,
        c.iso3 AS country_code_3, c.iso_numeric AS country_numeric_code,
        c.name AS country, c.continent_code,
        CASE c.continent_code WHEN 'AF' THEN 'Africa' WHEN 'AS' THEN 'Asia'
        WHEN 'EU' THEN 'Europe' WHEN 'NA' THEN 'North America'
        WHEN 'OC' THEN 'Oceania' WHEN 'SA' THEN 'South America'
        WHEN 'AN' THEN 'Antarctica' ELSE NULL END AS continent,
        p.admin1_code AS state_province_code, a1.name AS state_province,
        p.admin2_code AS county_district_code, a2.name AS county_district,
        p.admin3_code, p.admin4_code""" + joins + where + """
        ORDER BY p.population DESC, lower(p.name), p.geoname_id
        LIMIT %s OFFSET %s"""
    rows = db.execute(select, [*params, limit, offset]).fetchall()
    return rows, total
