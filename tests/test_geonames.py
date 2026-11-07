"""Focused unit tests for the GeoNames PostgreSQL integration helpers."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from weather_api.geonames import (
    ensure_geonames_schema, import_geonames_sqlite, search_geonames,
)


class FakeResult:
    def __init__(self, row=None, rows=None):
        self._row = row or {}
        self._rows = rows or []

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class FakeDB:
    def __init__(self):
        self.statements = []
        self.calls = 0

    def execute(self, sql, params=None):
        self.statements.append((sql, params or []))
        self.calls += 1
        if self.calls == 1:
            return FakeResult({"total": 2})
        return FakeResult(rows=[{"geoname_id": 123, "city": "Seattle"}])


class FakeCursor:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def executemany(self, sql, rows):
        rows = list(rows)
        self.db.inserts.append((sql, rows))


class SchemaDB:
    def __init__(self):
        self.statements = []
        self.inserts = []
        self.commits = 0
        self.rollbacks = 0

    def execute(self, sql):
        self.statements.append(sql)

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class GeoNamesTests(unittest.TestCase):
    def test_schema_creation_is_repeatable_and_keeps_geo_tables_separate(self):
        db = SchemaDB()
        ensure_geonames_schema(db)
        ensure_geonames_schema(db)
        sql = "\n".join(db.statements)
        self.assertIn("CREATE TABLE IF NOT EXISTS geo_countries", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS geo_admin1", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS geo_admin2", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS geo_places", sql)
        self.assertIn("CREATE INDEX IF NOT EXISTS idx_geo_places_name", sql)
        self.assertNotIn("DROP TABLE", sql)

    def test_sqlite_import_upserts_all_hierarchy_levels(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "locations.sqlite3"
            source = sqlite3.connect(path)
            source.executescript("""
                CREATE TABLE countries (
                    iso2, iso3, iso_numeric, fips_code, name, capital,
                    continent_code, languages, population, area_sq_km,
                    currency_code, tld, neighbours, geoname_id
                );
                CREATE TABLE admin1 (country_iso2, admin1_code, name, ascii_name, geoname_id);
                CREATE TABLE admin2 (country_iso2, admin1_code, admin2_code, name, ascii_name, geoname_id);
                CREATE TABLE places (
                    geoname_id, name, ascii_name, latitude, longitude, feature_code,
                    country_iso2, admin1_code, admin2_code, admin3_code, admin4_code,
                    population, elevation_m, dem_m, timezone, modified_date
                );
                INSERT INTO countries VALUES
                    ('US','USA','840','US','United States','Washington','NA','en',0,0,'USD','.us','CA',6252001);
                INSERT INTO admin1 VALUES ('US','WA','Washington','Washington',5815135);
                INSERT INTO admin2 VALUES ('US','WA','033','King County','King County',5799783);
                INSERT INTO places VALUES
                    (5809844,'Seattle','Seattle',47.6062,-122.3321,'PPL','US','WA','033','','',737015,56,0,'America/Los_Angeles','2026-01-01');
            """)
            source.close()

            db = SchemaDB()
            counts = import_geonames_sqlite(db, path, batch_size=1)
            self.assertEqual(counts, {"countries": 1, "admin1": 1, "admin2": 1, "places": 1})
            self.assertEqual(len(db.inserts), 4)
            self.assertTrue(all("ON CONFLICT" in sql for sql, _ in db.inserts))
            self.assertEqual(db.commits, 1)
            self.assertEqual(db.rollbacks, 0)

    def test_search_combines_hierarchy_filters_and_paginates_stably(self):
        db = FakeDB()
        rows, total = search_geonames(
            db,
            query="Seattle",
            continent="North America",
            country="United States",
            country_code="US",
            state="Washington",
            county="King County",
            city="Seattle",
            limit=25,
            offset=50,
        )
        self.assertEqual(total, 2)
        self.assertEqual(rows[0]["geoname_id"], 123)
        count_sql, count_params = db.statements[0]
        select_sql, select_params = db.statements[1]
        self.assertIn("JOIN geo_countries", count_sql)
        self.assertIn("LEFT JOIN geo_admin1", count_sql)
        self.assertIn("LEFT JOIN geo_admin2", count_sql)
        self.assertIn("ORDER BY p.population DESC, lower(p.name), p.geoname_id", select_sql)
        self.assertEqual(count_params, select_params[:-2])
        self.assertEqual(select_params[-2:], [25, 50])
        self.assertEqual(len(count_params), 14)


if __name__ == "__main__":
    unittest.main()
