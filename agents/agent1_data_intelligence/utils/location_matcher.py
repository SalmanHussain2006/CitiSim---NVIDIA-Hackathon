import json
import math


MONITORED_LOCATIONS = {
    "Liverpool Street": {
        "lat": 51.5178,
        "lon": -0.0823,
        "keywords": ["liverpool street", "bishopsgate", "broadgate"],
    },
    "Farringdon": {
        "lat": 51.5203,
        "lon": -0.1053,
        "keywords": ["farringdon", "smithfield", "charterhouse"],
    },
    "Bank": {
        "lat": 51.5133,
        "lon": -0.0890,
        "keywords": ["bank", "threadneedle", "poultry", "queen victoria street"],
    },
    "Moorgate": {
        "lat": 51.5186,
        "lon": -0.0886,
        "keywords": ["moorgate", "london wall"],
    },
    "Tower Hill": {
        "lat": 51.5098,
        "lon": -0.0766,
        "keywords": ["tower hill", "tower gateway", "tower bridge"],
    },
}


MATCH_RADIUS_KM = 1.0


def get_location_coordinates(name):
    loc = MONITORED_LOCATIONS.get(name)
    if not loc:
        return {"lat": None, "lon": None}
    return {"lat": loc["lat"], "lon": loc["lon"]}


def haversine_km(lat1, lon1, lat2, lon2):
    radius = 6371

    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    delta_p = math.radians(lat2 - lat1)
    delta_l = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_p / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(delta_l / 2) ** 2
    )

    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def extract_text_blob(obj):
    return json.dumps(obj).lower()


def extract_coordinates(item):
    possible_lat_keys = ["lat", "latitude"]
    possible_lon_keys = ["lon", "lng", "longitude"]

    if isinstance(item, dict):
        for lat_key in possible_lat_keys:
            for lon_key in possible_lon_keys:
                if lat_key in item and lon_key in item:
                    try:
                        return float(item[lat_key]), float(item[lon_key])
                    except Exception:
                        pass

        for value in item.values():
            result = extract_coordinates(value)
            if result:
                return result

    if isinstance(item, list):
        for value in item:
            result = extract_coordinates(value)
            if result:
                return result

    return None


def match_by_coordinates(item):
    coords = extract_coordinates(item)

    if not coords:
        return None

    lat, lon = coords

    best_location = None
    best_distance = 999

    for name, meta in MONITORED_LOCATIONS.items():
        distance = haversine_km(lat, lon, meta["lat"], meta["lon"])

        if distance < best_distance:
            best_location = name
            best_distance = distance

    if best_distance <= MATCH_RADIUS_KM:
        confidence = max(0.65, 1 - best_distance)
        return best_location, round(confidence, 2), "coordinate_match", round(best_distance, 3)

    return None


def match_by_keywords(item):
    text = extract_text_blob(item)

    for name, meta in MONITORED_LOCATIONS.items():
        for keyword in meta["keywords"]:
            if keyword in text:
                return name, 0.92, "keyword_match", None

    return None


def match_location(item):
    coordinate_match = match_by_coordinates(item)

    if coordinate_match:
        return coordinate_match

    keyword_match = match_by_keywords(item)

    if keyword_match:
        return keyword_match

    return None, 0.0, "no_match", None