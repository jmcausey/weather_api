#!/usr/bin/env python3
import time

from weather_api import create_app
from weather_api.tasks import run_due_weather_jobs

app = create_app()

if __name__ == "__main__":
    print("Starting weather API scheduler")
    while True:
        with app.app_context():
            results = run_due_weather_jobs()
        if results:
            print(f"Ran weather jobs: {results}")
        time.sleep(30)
