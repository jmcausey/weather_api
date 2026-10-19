import json
import requests

def get_tempest_data(station_id="156550"):
    # WeatherFlow provides public observations via their REST API
    # Public stations can often be accessed directly or via token. 
    url = f"https://swd.weatherflow.com/swd/rest/observations/station/{station_id}"
    
    print(f"Fetching data for Station {station_id}...")
    
    try:
        response = requests.get(url)
        
        # If the station requires a token, you can pass ?token=YOUR_TOKEN
        if response.status_code == 401:
            print("Error: This station requires a Personal Access Token.")
            print("Get one free via Tempest Web App -> Settings -> Data Authorizations.")
            return
            
        response.raise_for_status()
        data = response.json()
        
        # Pretty print the structured JSON response
        print(json.dumps(data, indent=4))
        
    except Exception as e:
        print(f"Failed to fetch station data: {e}")

if __name__ == "__main__":
    get_tempest_data("156550")
