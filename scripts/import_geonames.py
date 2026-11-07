#!/usr/bin/env python3
"""Import a built locations SQLite database into weather_api PostgreSQL."""
import argparse
import os

import psycopg

from weather_api.geonames import import_geonames_sqlite


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", default="data/locations/locations.sqlite3",
                        help="Path to the database built by jmcausey/locations")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"),
                        help="PostgreSQL URL (defaults to DATABASE_URL)")
    args = parser.parse_args()
    if not args.database_url:
        parser.error("set DATABASE_URL or pass --database-url")
    with psycopg.connect(args.database_url, row_factory=psycopg.rows.dict_row) as db:
        counts = import_geonames_sqlite(db, args.sqlite)
    print("GeoNames import complete: " + ", ".join(
        f"{name}={count:,}" for name, count in counts.items()
    ))


if __name__ == "__main__":
    main()
