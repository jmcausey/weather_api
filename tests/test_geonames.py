"""Focused unit tests for the GeoNames PostgreSQL integration helpers."""
import unittest

from weather_api.geonames import ensure_geonames_schema, search_geonames


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


class SchemaDB:
    def __init__(self):
        self.statements = []

    def execute(self, sql):
        self.statements.append(sql)


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
        self.assertEqual(len(count_params), 11)


if __name__ == "__main__":
    unittest.main()
