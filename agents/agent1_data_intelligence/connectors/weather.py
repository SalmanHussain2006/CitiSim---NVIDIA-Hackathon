import requests


def pull_weather():
    response = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": 51.5155,
            "longitude": -0.0922,
            "hourly": "temperature_2m,precipitation,rain,wind_speed_10m",
            "forecast_days": 2,
            "timezone": "Europe/London",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()