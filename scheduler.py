#!/usr/bin/env python3
import time
import traceback

from weather_api import create_app
from weather_api.tasks import run_due_weather_jobs
from weather_api.tempest_jobs import run_due_tempest_jobs

app = create_app()


if __name__ == "__main__":
    print("Starting weather API scheduler", flush=True)
    while True:
        try:
            with app.app_context():
                weather_results = run_due_weather_jobs()
                tempest_results = run_due_tempest_jobs()
            if weather_results:
                print(f"Ran weather jobs: {weather_results}", flush=True)
            if tempest_results:
                print(f"Ran Tempest jobs: {tempest_results}", flush=True)
        except Exception:
            # Keep scheduler alive, but make database/query/collection failures visible.
            traceback.print_exc()
        time.sleep(30)
