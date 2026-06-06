import json
import time
from pathlib import Path
from datetime import datetime, timezone

from connectors.tfl import pull_road_disruptions, pull_line_status
from connectors.weather import pull_weather
from connectors.air_quality import pull_air_quality_sites
from connectors.footfall import pull_footfall
from connectors.events import pull_city_events
from connectors.planning import pull_planning_data

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
                                "note": "Line-level TfL disruption applied to monitored hubs.",
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


def analyse_air_quality_sites(data):
    # For now, this stores LAQN monitoring metadata as a low-severity intelligence event.
    # Next upgrade: pull latest readings from selected stations and detect NO2 / PM2.5 alerts.
    return [
        create_event(
            event_type="air_quality_monitoring_available",
            location="City of London",
            coordinates={"lat": 51.5155, "lon": -0.0922},
            severity="low",
            confidence=0.9,
            summary="London air quality monitoring site metadata was ingested.",
            data={"raw": data},
        )
    ]


def analyse_footfall(items):
    events = []

    for item in items:
        location = item.get("location")
        count = item.get("footfall_count", 0)
        baseline = item.get("baseline", 1)

        if not location:
            continue

        ratio = count / baseline if baseline else 0

        if ratio >= 1.25:
            severity = "high"
        elif ratio >= 1.1:
            severity = "medium"
        else:
            severity = "low"

        events.append(
            create_event(
                event_type="footfall_signal",
                location=location,
                coordinates=get_location_coordinates(location),
                severity=severity,
                confidence=0.8,
                summary=f"Footfall at {location} is {round(ratio, 2)}x baseline.",
                data=item,
            )
        )

    return events


def analyse_city_events(items):
    events = []

    for item in items:
        location = item.get("location")
        attendance = item.get("expected_attendance", 0)
        name = item.get("name", "City event")

        if not location:
            continue

        severity = "high" if attendance >= 7500 else "medium"

        events.append(
            create_event(
                event_type="city_event_pressure",
                location=location,
                coordinates=get_location_coordinates(location),
                severity=severity,
                confidence=0.78,
                summary=f"{name} may increase movement pressure around {location}.",
                data=item,
            )
        )

    return events


def analyse_planning(items):
    events = []

    for item in items:
        location = item.get("location")
        impact = item.get("impact", "medium")
        project_type = item.get("project_type", "planning_project")
        description = item.get("description", "Planning or infrastructure activity detected.")

        if not location:
            continue

        events.append(
            create_event(
                event_type="planning_infrastructure_signal",
                location=location,
                coordinates=get_location_coordinates(location),
                severity=impact,
                confidence=0.74,
                summary=f"{project_type} near {location}: {description}",
                data=item,
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
        roads = pull_road_disruptions()
        save_json(RAW_DIR, "tfl_road_disruptions", roads)
        road_events = analyse_road_disruptions(roads)
        events.extend(road_events)
        print(f"Road events: {len(road_events)}")
    except Exception as error:
        print(f"Road API failed: {error}")

    try:
        lines = pull_line_status()
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

    try:
        air_quality = pull_air_quality_sites()
        save_json(RAW_DIR, "air_quality_sites", air_quality)
        aq_events = analyse_air_quality_sites(air_quality)
        events.extend(aq_events)
        print(f"Air quality events: {len(aq_events)}")
    except Exception as error:
        print(f"Air quality API failed: {error}")

    try:
        footfall = pull_footfall()
        save_json(RAW_DIR, "footfall", footfall)
        footfall_events = analyse_footfall(footfall)
        events.extend(footfall_events)
        print(f"Footfall events: {len(footfall_events)}")
    except Exception as error:
        print(f"Footfall pull failed: {error}")

    try:
        city_events = pull_city_events()
        save_json(RAW_DIR, "city_events", city_events)
        city_event_signals = analyse_city_events(city_events)
        events.extend(city_event_signals)
        print(f"City event signals: {len(city_event_signals)}")
    except Exception as error:
        print(f"City events pull failed: {error}")

    try:
        planning = pull_planning_data()
        save_json(RAW_DIR, "planning", planning)
        planning_events = analyse_planning(planning)
        events.extend(planning_events)
        print(f"Planning events: {len(planning_events)}")
    except Exception as error:
        print(f"Planning pull failed: {error}")

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