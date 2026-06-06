import requests


def pull_air_quality_sites():
    response = requests.get(
        "https://api.erg.ic.ac.uk/AirQuality/Information/MonitoringSites/GroupName=London/Json",
        timeout=30,
    )
    response.raise_for_status()
    return response.json()