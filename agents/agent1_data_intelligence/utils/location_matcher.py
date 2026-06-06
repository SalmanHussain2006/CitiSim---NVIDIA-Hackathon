import json

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


def get_location_coordinates(name):
    loc = MONITORED_LOCATIONS.get(name)
    if not loc:
        return {"lat": None, "lon": None}
    return {"lat": loc["lat"], "lon": loc["lon"]}


def extract_text_blob(obj):
    return json.dumps(obj).lower()


def match_location(item):
    text = extract_text_blob(item)

    for name, meta in MONITORED_LOCATIONS.items():
        for keyword in meta["keywords"]:
            if keyword in text:
                return name, 0.92, "keyword_match"

    return None, 0.0, "no_match"