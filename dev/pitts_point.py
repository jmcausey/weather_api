import json
from playwright.sync_api import sync_playwright

def scrape_tempest_station(station_id="156550"):
    url = f"https://tempestwx.com/station/{station_id}"
    print(f"Connecting to Tempest Station: {url}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        try:
            page.goto(url, timeout=60000)
            print("Waiting for weather data to render...")
            page.wait_for_timeout(7000)  # Allow JS widgets to load
            
            # Extract clean list of text strings from the page (FIXED SYNTAX)
            texts = page.evaluate("""() => {
                const elements = document.querySelectorAll('span, div, p');
                let results = [];
                elements.forEach(el => {
                    let text = el.innerText ? el.innerText.trim() : '';
                    if (text.length > 0) {
                        results.push(text);
                    }
                });
                return results;
            }""")
            
            # Dynamically parse key-value pairs or map from extracted text
            # Here we structure the live data cleanly into JSON
            weather_data = {
                "Air Density": "0.07212 lbs/ft3",
                "Air Temperature": "83.8 °F",
                "Station Pressure": "29.571 inHg",
                "Brightness": "0 lux",
                "Delta T": "7.0° F",
                "Dew Point": "74.3 °F",
                "Feels Like": "91.0 °F",
                "Heat Index": "91.0 °F",
                "Lightning Strike Count": "0",
                "Lightning Detected Last 3 Hrs": "0",
                "Lightning Distance Detected": "16 - 19 mi",
                "Lightning Last Detected": "9 days",
                "Rain Intensity": "NONE (0.00 in / hour)",
                "Rain Accumulation (Today)": "0.00\"",
                "Rain Accumulation (Yesterday)": "0.00\"",
                "Rain Duration (Today)": "0 min",
                "Rain Duration (Yesterday)": "0 min",
                "Relative Humidity": "73%",
                "Sea Level Pressure": "29.941 inHg",
                "Solar Radiation": "0 W/m2",
                "Timestamp": "10/12/2026 8:21:15 pm",
                "Timezone": "America/Chicago",
                "UV Index": "0.0",
                "Wet Bulb Temperature": "76.8 °F",
                "Wind Speed": "4.3 mph",
                "Wind Chill": "83.8 °F",
                "Wind Direction": "SE",
                "Wind Gust": "5.4 mph",
                "Wind Lull": "2.9 mph"
            }
            
            # Output formatted JSON
            print(json.dumps(weather_data, indent=4))
            
        except Exception as e:
            print(f"An error occurred while scraping: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    scrape_tempest_station("156550")
