# Import required libraries
# Flask - web framework for running the server and serving pages
# render_template - loads HTML files from the templates folder
# request - reads data sent from the browser (like the city name)
# jsonify - converts Python dictionaries to JSON to send back to the browser
# session - stores data between requests (used for saving cities)
from flask import Flask, render_template, request, jsonify, session

# requests - used to make HTTP calls to the OpenWeatherMap API
import requests

# Initialize the Flask application
app = Flask(__name__)

# Secret key required by Flask to encrypt session data (saved cities)
app.secret_key = "weather_dashboard_secret_key"

# OpenWeatherMap API key
API_KEY = "e78474a15dd3f0f32559bd6f7ff8db1a"

# Base URL for all OpenWeatherMap API requests
BASE_URL = "https://api.openweathermap.org/data/2.5"

def get_weather(city, units="imperial"):
    """
    Fetches current weather data for a given city.
    - city: the city name (e.g. 'Gardner, KS, US')
    - units: 'imperial' for fahrenheit, 'metric' for celsius
    Returns the JSON response and HTTP status code.
    """
    # Build the full API endpoint URL for current weather
    url = f"{BASE_URL}/weather"

    # Define the parameters to send with the request
    params = {
        "q": city,        # City name to search
        "appid": API_KEY, # API key for authentication
        "units": units    # Unit system for temperature
    }

    # Make the GET request to the API and return the response
    response = requests.get(url, params=params)
    return response.json(), response.status_code

def get_forecast(city, units="imperial"):
    """
    Fetches a 5-day weather forecast for a given city.
    The API returns data in 3-hour intervals, so cnt=40 gives ~5 days.
    Returns the JSON response and HTTP status code.
    """
    # Build the full API endpoint URL for forecast data
    url = f"{BASE_URL}/forecast"

    # Define the parameters to send with the request
    params = {
        "q": city,
        "appid": API_KEY,
        "units": units,
        "cnt": 40  # 40 x 3-hour intervals = ~5 days of forecast data
    }

    # Make the GET request to the API and return the response
    response = requests.get(url, params=params)
    return response.json(), response.status_code

def get_alerts(lat, lon):
    """
    Fetches severe weather alerts for a location using the One Call API.
    Takes latitude and longitude coordinates instead of city name,
    since the alerts endpoint requires coordinates.
    Returns a list of alerts with event name and description.
    """
    # The alerts endpoint is part of the One Call API, separate from the base URL
    url = "https://api.openweathermap.org/data/3.0/onecall"

    # Define the parameters to send with the request
    params = {
        "lat": lat,   # Latitude coordinate of the city
        "lon": lon,   # Longitude coordinate of the city
        "appid": API_KEY,
        # Exclude everything except alerts to keep the response small
        "exclude": "current,minutely,hourly,daily"
    }

    response = requests.get(url, params=params)

    if response.status_code == 200:
        data = response.json()
        # Extract the alerts list, defaulting to empty if none exist
        alerts = data.get("alerts", [])
        # Return just the event name and a trimmed description (max 300 chars)
        return [{"event": a["event"], "description": a["description"][:300]} for a in alerts]

    # Return empty list if no alerts or if the request failed
    return []

def parse_forecast(forecast_data):
    """
    Processes raw forecast API data into clean daily summaries.
    Groups 3-hour intervals by day and calculates:
    - Min and max temperature for the day
    - Most common weather description
    - A representative weather icon
    Returns a list of up to 5 daily forecast dictionaries.
    """
    # Dictionary to group forecast intervals by date
    daily = {}

    for item in forecast_data.get("list", []):
        # Each item has a datetime string like "2024-01-15 12:00:00"
        # Split on the space and take just the date portion
        date = item["dt_txt"].split(" ")[0]

        # Create an entry for this date if it doesn't exist yet
        if date not in daily:
            daily[date] = {
                "temps": [],
                "descriptions": [],
                "icons": [],
                "humidity": []
            }

        # Append this 3-hour interval's data to the day's running lists
        daily[date]["temps"].append(item["main"]["temp"])
        daily[date]["descriptions"].append(item["weather"][0]["description"])
        daily[date]["icons"].append(item["weather"][0]["icon"])
        daily[date]["humidity"].append(item["main"]["humidity"])

    # Condense each day's list of intervals into a single summary
    result = []
    for date, data in list(daily.items())[:5]:
        result.append({
            "date": date,
            "min_temp": round(min(data["temps"])),
            "max_temp": round(max(data["temps"])),
            # Pick the most frequently occurring description for the day
            "description": max(set(data["descriptions"]), key=data["descriptions"].count),
            # Use the middle icon of the day as a representative icon
            "icon": data["icons"][len(data["icons"]) // 2],
            "humidity": round(sum(data["humidity"]) / len(data["humidity"]))
        })
    return result

# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """
    Renders the main page of the app.
    Passes any saved cities from the session to the HTML template
    so they can be displayed as quick-access chips.
    """
    # Retrieve saved cities from the session, defaulting to an empty list
    saved_cities = session.get("saved_cities", [])

    # Load and return the main HTML page, passing in the saved cities
    return render_template("index.html", saved_cities=saved_cities)

@app.route("/weather", methods=["GET"])
def weather():
    """
    Main weather endpoint. Called by the frontend when a city is searched.
    Fetches current weather, forecast, and any severe weather alerts.
    Returns all data as JSON to be rendered dynamically in the browser.
    """
    # Read the city and units from the search request
    city = request.args.get("city", "").strip()
    units = request.args.get("units", "imperial")

    # Return an error if no city was provided
    if not city:
        return jsonify({"error": "Please enter a city name."}), 400

    # Fetch current weather and handle any errors
    weather_data, status = get_weather(city, units)
    if status != 200:
        msg = weather_data.get("message", "City not found.")
        return jsonify({"error": f"Could not find weather for '{city}': {msg}"}), status

    # Fetch and parse the 5-day forecast
    forecast_data, f_status = get_forecast(city, units)
    forecast = parse_forecast(forecast_data) if f_status == 200 else []

    # Pull coordinates from the weather response to use for alerts
    lat = weather_data["coord"]["lat"]
    lon = weather_data["coord"]["lon"]
    alerts = get_alerts(lat, lon)

    # Set the correct unit labels based on the selected unit system
    unit_symbol = "°F" if units == "imperial" else "°C"
    wind_unit = "mph" if units == "imperial" else "m/s"

    # Build and return the full response dictionary as JSON
    result = {
        "city": weather_data["name"],
        "country": weather_data["sys"]["country"],
        "temp": round(weather_data["main"]["temp"]),
        "feels_like": round(weather_data["main"]["feels_like"]),
        "description": weather_data["weather"][0]["description"].title(),
        "icon": weather_data["weather"][0]["icon"],
        "humidity": weather_data["main"]["humidity"],
        "wind_speed": round(weather_data["wind"]["speed"]),
        "visibility": round(weather_data.get("visibility", 0) / 1000, 1),
        "pressure": weather_data["main"]["pressure"],
        "unit_symbol": unit_symbol,
        "wind_unit": wind_unit,
        "forecast": forecast,
        "alerts": alerts,
        "units": units
    }
    return jsonify(result)

@app.route("/save_city", methods=["POST"])
def save_city():
    """
    Saves a city to the session so it appears as a quick-access chip.
    Receives the city name as JSON in the request body.
    Avoids duplicates before appending.
    """
    # Read the city name from the request body
    city = request.json.get("city", "").strip()

    # Return an error if no city was provided
    if not city:
        return jsonify({"error": "No city provided"}), 400

    # Get the current saved cities list from the session
    saved = session.get("saved_cities", [])

    # Only add the city if it isn't already saved
    if city not in saved:
        saved.append(city)
        session["saved_cities"] = saved

    return jsonify({"saved_cities": saved})


@app.route("/remove_city", methods=["POST"])
def remove_city():
    """
    Removes a city from the saved cities session list.
    Receives the city name as JSON in the request body.
    """
    # Read the city name from the request body
    city = request.json.get("city", "").strip()

    # Get the current saved cities list from the session
    saved = session.get("saved_cities", [])

    # Remove the city if it exists in the list
    if city in saved:
        saved.remove(city)
        session["saved_cities"] = saved

    return jsonify({"saved_cities": saved})

# ── Entry Point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # debug=True enables auto-reloading when code changes are saved
    app.run(debug=True)