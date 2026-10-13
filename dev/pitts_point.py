"""Standalone smoke test for the API's live Tempest scraper."""
import json
from datetime import datetime

from weather_api.tempest import scrape_tempest_station


if __name__ == "__main__":
    import sys

    station_id = sys.argv[1] if len(sys.argv) > 1 else "156550"
    observation = scrape_tempest_station(station_id)
    print(json.dumps(observation, indent=2, default=lambda v: v.isoformat() if isinstance(v, datetime) else str(v)))
