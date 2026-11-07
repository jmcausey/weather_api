#!/usr/bin/env python3
"""
Interactive browser for the weather_api locations resource.

The browser builds cascading Region -> Country -> State -> City menus from
GET /api/v1/locations and returns the selected location records, including
all fields supplied by the API.

Current API contract (see docs/api-reference.md) returns:
    display_name, name, region, latitude, longitude

If the API later adds explicit country/state/city fields, this client uses
them automatically. With the current response, it derives a country from
"display_name" and recognizes US state abbreviations. It does not invent
continent/region data that the API does not provide.

Usage:
    python scripts/location_browser.py
    python scripts/location_browser.py --base-url http://localhost:5000
    python scripts/location_browser.py --query Washington
    python scripts/location_browser.py --json
    python scripts/location_browser.py --limit 500

Requires:
    pip install requests
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from typing import Any

import requests


US_STATE_CODES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
}
US_COUNTRY_NAMES = {"US", "USA", "UNITED STATES", "UNITED STATES OF AMERICA"}


class LocationsAPI:
    def __init__(self, base_url: str, timeout: float = 20.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})

    def search(self, query: str = "", limit: int = 500) -> list[dict[str, Any]]:
        """Fetch every matching page so interactive selection is not limited to 500 rows."""
        items: list[dict[str, Any]] = []
        offset = 0
        while True:
            response = self.session.get(
                f"{self.base_url}/api/v1/locations",
                params={"q": query, "limit": limit, "offset": offset},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
                raise ValueError("Unexpected locations response; expected an object with an 'items' list")
            page = [row for row in payload["items"] if isinstance(row, dict)]
            items.extend(page)
            if not payload.get("has_more", len(page) == limit) or not page:
                break
            offset += len(page)
        return items

    def get_available_data(self, location: dict[str, Any]) -> dict[str, Any]:
        """Return the complete location record exactly as supplied by the API."""
        return dict(location)


def _first_nonempty(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def normalize_location(row: dict[str, Any]) -> dict[str, Any]:
    """Preserve API fields and build a consistent hierarchy for the menus."""
    item = dict(row)
    display = str(_first_nonempty(item, "display_name", "name", "city") or "").strip()
    parts = [part.strip() for part in display.rsplit(",", 1)]
    suffix = parts[-1] if len(parts) == 2 else ""

    city = str(_first_nonempty(item, "city", "name") or (parts[0] if parts else display))
    region = str(_first_nonempty(item, "region") or "")
    country = str(_first_nonempty(item, "country") or suffix or "Unknown")
    state = str(_first_nonempty(item, "state") or "")

    # Compatibility for older API deployments that do not yet return normalized fields.
    if not item.get("country") and suffix.upper() in US_STATE_CODES:
        country = "United States"
    if not item.get("state") and suffix.upper() in US_STATE_CODES:
        state = suffix

    item.setdefault("display_name", display or city)
    item.setdefault("city", city)
    item.setdefault("country", country)
    item.setdefault("state", state or None)
    item["hierarchy"] = {
        "region": region or (state or country),
        "country": country,
        "state": state or None,
        "city": city,
    }
    return item


def choose_from_list(label: str, values: list[str], allow_all: bool = True) -> str | None:
    if not values:
        print(f"No {label.lower()} values available.")
        return None

    print(f"\n{label}:")
    if allow_all:
        print("  0) [All]")
    for index, value in enumerate(values, start=1):
        print(f"  {index}) {value}")

    while True:
        answer = input(f"Select {label.lower()} (number, Enter to skip, q to quit): ").strip()
        if answer.lower() == "q":
            raise KeyboardInterrupt
        if not answer:
            return None
        if allow_all and answer == "0":
            return "__ALL__"
        if answer.isdigit() and 1 <= int(answer) <= len(values):
            return values[int(answer) - 1]
        print("Please enter one of the displayed numbers, Enter, or q.")


def filter_by(items: list[dict[str, Any]], key: str, value: str | None) -> list[dict[str, Any]]:
    if value in (None, "__ALL__"):
        return items
    return [
        item for item in items
        if str(item.get("hierarchy", {}).get(key) or "") == value
    ]


def cascade_select(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Interactively narrow results from region to country, state, then city."""
    selected = items

    levels = (
        ("region", "Region"),
        ("country", "Country"),
        ("state", "State"),
        ("city", "City"),
    )
    for key, label in levels:
        values = sorted({
            str(item.get("hierarchy", {}).get(key))
            for item in selected
            if item.get("hierarchy", {}).get(key) not in (None, "")
        }, key=str.casefold)

        # State is not meaningful for countries that do not expose states.
        if key == "state" and not values:
            continue
        if len(values) <= 1:
            if values:
                selected = filter_by(selected, key, values[0])
                print(f"{label}: {values[0]} (only available value)")
            continue

        choice = choose_from_list(label, values)
        if choice is None:
            continue
        if choice == "__ALL__":
            continue
        selected = filter_by(selected, key, choice)
        print(f"{len(selected)} location(s) remain.")

        if not selected:
            break

    return selected


def select_locations(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Allow one or more explicit location selections from the filtered list."""
    if not items:
        return []

    print(f"\nMatching locations ({len(items)}):")
    for index, item in enumerate(items, start=1):
        lat = item.get("latitude", "n/a")
        lon = item.get("longitude", "n/a")
        print(f"  {index:>4}) {item.get('display_name', item.get('name', 'Unknown'))} "
              f"[{lat}, {lon}]")

    print("\nEnter comma-separated numbers, 'all', or Enter for none.")
    while True:
        answer = input("Locations to return: ").strip()
        if not answer:
            return []
        if answer.lower() == "all":
            return items
        try:
            indexes = list(dict.fromkeys(int(part.strip()) for part in answer.split(",")))
            if not indexes or any(index < 1 or index > len(items) for index in indexes):
                raise ValueError
            return [items[index - 1] for index in indexes]
        except ValueError:
            print(f"Enter numbers from 1 to {len(items)}, separated by commas, or 'all'.")


def build_nested_result(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Group selected full records into Region/Country/State/City nested lists."""
    result: dict[str, Any] = {}
    for item in items:
        h = item["hierarchy"]
        region = h["region"]
        country = h["country"]
        state = h["state"] or "(no state)"
        city = h["city"]
        result.setdefault(region, {}).setdefault(country, {}).setdefault(state, []).append(
            {"city": city, "location": item}
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Search and select locations from weather_api.")
    parser.add_argument("--base-url", default="http://localhost:5000",
                        help="API root URL (default: http://localhost:5000)")
    parser.add_argument("--query", default=None,
                        help="Initial API search term; omit to enter it interactively")
    parser.add_argument("--limit", type=int, default=500,
                        help="Maximum API results (1-500; default: 500)")
    parser.add_argument("--json", action="store_true",
                        help="Print selected records and nested groups as JSON")
    parser.add_argument("--nested-only", action="store_true",
                        help="Print only the nested Region/Country/State/City result")
    args = parser.parse_args()
    limit = min(max(args.limit, 1), 500)

    try:
        api = LocationsAPI(args.base_url)
        query = args.query
        if query is None:
            query = input("Search locations (blank searches the first API page): ").strip()

        raw_items = api.search(query, limit)
        items = [normalize_location(row) for row in raw_items]
        if not items:
            print("The API returned no matching locations.")
            return 0

        if args.json:
            selected = items
        else:
            print(f"Retrieved {len(items)} location(s) from {args.base_url}/api/v1/locations")
            filtered = cascade_select(items)
            selected = select_locations(filtered)

        records = [api.get_available_data(item) for item in selected]
        nested = build_nested_result(records)

        if args.nested_only:
            print(json.dumps(nested, indent=2, ensure_ascii=False))
        elif args.json:
            print(json.dumps({"count": len(records), "items": records, "groups": nested},
                             indent=2, ensure_ascii=False))
        else:
            print(f"\nSelected {len(records)} location(s).")
            print("\nFlat list (each item contains the API fields plus normalized hierarchy):")
            print(json.dumps(records, indent=2, ensure_ascii=False))
            print("\nNested Region -> Country -> State -> City list:")
            print(json.dumps(nested, indent=2, ensure_ascii=False))

        return 0
    except requests.RequestException as exc:
        print(f"API request failed: {exc}", file=sys.stderr)
        return 1
    except (ValueError, KeyError) as exc:
        print(f"Could not process API response: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nSelection cancelled.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
