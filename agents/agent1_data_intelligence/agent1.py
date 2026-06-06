import json
import time
import requests
from pathlib import Path
from datetime import datetime, timezone

from utils.event_schema import create_event
from utils.location_matcher import (
    MONITORED_LOCATIONS,
    match_location,
    get_location_coordinates,
)

BASE = Path(__file__).resolve().parents[2]
RAW_DIR = BASE / "data" / "raw"
EVENT_DIR = BASE / "data" / "events"

RAW_DIR.mkdir(parents=True, exist_ok=True)
EVENT_DIR.mkdir(parents=True, exist_ok=True)


def ts():
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def save_json(folder, name, data):
    path = folder / f"{name}_{ts()}.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def get_json(url, params=None):
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def pull_tfl_roads():
    return get_json("https://api.tfl.gov.uk/Road/All/Disruption")


def pull_tfl_lines():
    return get_json(
        "https://api.tfl.gov.uk/Line/Mode/tube,dlr,elizabeth-line,overground/Status"
    )


def pull_weather():
    return get_json(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": 51.5155,
            "longitude": -0.0922,
            "hourly": "temperature_2m,precipitation,rain,wind_speed_10m",
            "forecast_days": 2,
            "timezone": "Europe/London",
        },
    )


def analyse_road_disruptions(items):
    events = []

    for item in items:
        location, confidence, match_method, distance_km = match_location(item)

        if not location:
            continue

        severity_raw = str(item.get("severity", "")).lower()
        category = item.get("category", "road_disruption")
        description = (
            item.get("comments")
            or item.get("description")
            or "Road disruption detected."
        )

        severity = "medium"
        if any(word in severity_raw for word in ["serious", "severe", "critical", "closure"]):
            severity = "high"

        events.append(
            create_event(
                event_type="road_disruption",
                location=location,
                coordinates=get_location_coordinates(location),
                severity=severity,
                confidence=confidence,
                summary=f"Road disruption near {location}: {category}. {description}",
                data={
                    "match_method": match_method,
                    "distance_km": distance_km,
                    "raw": item,
                },
            )
        )

    return events


def analyse_transport_status(lines):
    events = []

    for line in lines:
        line_name = line.get("name", "Unknown line")
        statuses = line.get("lineStatuses", [])

        for status in statuses:
            desc = status.get("statusSeverityDescription", "")
            reason = status.get("reason", "")

            if desc.lower() not in ["good service", ""]:
                for location in MONITORED_LOCATIONS:
                    events.append(
                        create_event(
                            event_type="transport_disruption_risk",
                            location=location,
                            coordinates=get_location_coordinates(location),
                            severity="high" if "severe" in desc.lower() else "medium",
                            confidence=0.72,
                            summary=f"{line_name} disruption may affect {location}: {desc}. {reason}",
                            data={
                                "line": line_name,
                                "status": status,
                            },
                        )
                    )

    return events


def analyse_weather(weather):
    events = []
    hourly = weather.get("hourly", {})

    times = hourly.get("time", [])
    rain = hourly.get("rain", [])
    precipitation = hourly.get("precipitation", [])
    wind = hourly.get("wind_speed_10m", [])

    for i, forecast_time in enumerate(times[:24]):
        rain_mm = rain[i] if i < len(rain) else 0
        precip_mm = precipitation[i] if i < len(precipitation) else 0
        wind_speed = wind[i] if i < len(wind) else 0

        if rain_mm >= 4 or precip_mm >= 4:
            for location in MONITORED_LOCATIONS:
                events.append(
                    create_event(
                        event_type="weather_congestion_risk",
                        location=location,
                        coordinates=get_location_coordinates(location),
                        severity="medium",
                        confidence=0.75,
                        summary=f"Rain forecast near {location} around {forecast_time}; congestion and footfall disruption risk increases.",
                        data={
                            "forecast_time": forecast_time,
                            "rain_mm": rain_mm,
                            "precipitation_mm": precip_mm,
                        },
                    )
                )

        if wind_speed >= 35:
            for location in MONITORED_LOCATIONS:
                events.append(
                    create_event(
                        event_type="weather_pedestrian_risk",
                        location=location,
                        coordinates=get_location_coordinates(location),
                        severity="medium",
                        confidence=0.7,
                        summary=f"High wind forecast near {location} around {forecast_time}; pedestrian and cycling disruption risk increases.",
                        data={
                            "forecast_time": forecast_time,
                            "wind_speed_10m": wind_speed,
                        },
                    )
                )

    return events


def monitoring_snapshots():
    events = []

    for location in MONITORED_LOCATIONS:
        events.append(
            create_event(
                event_type="location_monitoring_snapshot",
                location=location,
                coordinates=get_location_coordinates(location),
                severity="low",
                confidence=1.0,
                summary=f"Agent 1 is actively monitoring {location}.",
                data={
                    "location_profile": MONITORED_LOCATIONS[location],
                },
            )
        )

    return events


def run_once():
    print("Urban Pulse Agent 1 starting...")
    events = []

    events.extend(monitoring_snapshots())

    try:
        roads = pull_tfl_roads()
        save_json(RAW_DIR, "tfl_road_disruptions", roads)
        road_events = analyse_road_disruptions(roads)
        events.extend(road_events)
        print(f"Road events: {len(road_events)}")
    except Exception as error:
        print(f"Road API failed: {error}")

    try:
        lines = pull_tfl_lines()
        save_json(RAW_DIR, "tfl_line_status", lines)
        line_events = analyse_transport_status(lines)
        events.extend(line_events)
        print(f"Transport events: {len(line_events)}")
    except Exception as error:
        print(f"TfL line API failed: {error}")

    try:
        weather = pull_weather()
        save_json(RAW_DIR, "weather", weather)
        weather_events = analyse_weather(weather)
        events.extend(weather_events)
        print(f"Weather events: {len(weather_events)}")
    except Exception as error:
        print(f"Weather API failed: {error}")

    batch_path = save_json(EVENT_DIR, "agent1_events", events)

    for event in events:
        event_path = EVENT_DIR / f"{event['id']}.json"
        event_path.write_text(json.dumps(event, indent=2), encoding="utf-8")

    print(f"Saved {len(events)} events to {batch_path}")
    return events


def run_loop(minutes=5):
    while True:
        run_once()
        print(f"Sleeping {minutes} minutes...")
        time.sleep(minutes * 60)


if __name__ == "__main__":
    run_once()