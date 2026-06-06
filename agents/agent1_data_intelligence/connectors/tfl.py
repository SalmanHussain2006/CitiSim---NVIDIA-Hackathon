import requests


def get_json(url, params=None):
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def pull_road_disruptions():
    return get_json("https://api.tfl.gov.uk/Road/All/Disruption")


def pull_line_status():
    return get_json(
        "https://api.tfl.gov.uk/Line/Mode/tube,dlr,elizabeth-line,overground/Status"
    )