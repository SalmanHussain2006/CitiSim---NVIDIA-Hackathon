import json
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict


BASE = Path(__file__).resolve().parents[2]
EVENT_DIR = BASE / "data" / "events"
OUTPUT_DIR = BASE / "data" / "recommendations"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def load_events():
    batch_files = sorted(
        EVENT_DIR.glob("agent1_events_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if not batch_files:
        return []

    latest_file = batch_files[0]
    print(f"Using latest Agent 1 batch: {latest_file.name}")

    try:
        return json.loads(latest_file.read_text(encoding="utf-8"))
    except Exception as error:
        print(f"Failed to load latest event batch: {error}")
        return []


def group_by_location(events):
    grouped = defaultdict(list)

    for event in events:
        location = event.get("location", "Unknown")
        grouped[location].append(event)

    return grouped


def make_recommendation(
    location,
    priority,
    recommendation_type,
    title,
    action,
    reasoning,
    predicted_outcome,
    source_events,
):
    return {
        "id": f"rec_{location.lower().replace(' ', '_')}_{recommendation_type}",
        "source_agent": "agent_4_recommendation",
        "timestamp": now_iso(),
        "location": location,
        "priority": priority,
        "recommendation_type": recommendation_type,
        "title": title,
        "action": action,
        "reasoning": reasoning,
        "predicted_outcome": predicted_outcome,
        "source_event_ids": [e.get("id") for e in source_events],
    }


def generate_recommendations(events):
    recommendations = []
    grouped = group_by_location(events)

    for location, location_events in grouped.items():
        event_types = {e.get("event_type") for e in location_events}

        road_events = [e for e in location_events if e.get("event_type") == "road_disruption"]
        transport_events = [e for e in location_events if e.get("event_type") == "transport_disruption_risk"]
        footfall_events = [e for e in location_events if e.get("event_type") == "footfall_signal"]
        city_event_pressure = [e for e in location_events if e.get("event_type") == "city_event_pressure"]
        planning_events = [e for e in location_events if e.get("event_type") == "planning_infrastructure_signal"]
        weather_events = [
            e for e in location_events
            if e.get("event_type") in ["weather_congestion_risk", "weather_pedestrian_risk"]
        ]

        if road_events and transport_events:
            recommendations.append(
                make_recommendation(
                    location=location,
                    priority="high",
                    recommendation_type="traffic_management",
                    title=f"Reduce combined road and transport disruption near {location}",
                    action="Deploy temporary traffic management and monitor station-area crowding.",
                    reasoning=[
                        "Road disruption is active near this location.",
                        "Public transport disruption risk is also present.",
                        "Combined signals increase congestion and pedestrian crowding risk.",
                    ],
                    predicted_outcome={
                        "congestion_reduction_estimate": "10-18%",
                        "crowding_risk_reduction": "medium",
                    },
                    source_events=road_events + transport_events,
                )
            )

        if road_events and footfall_events:
            recommendations.append(
                make_recommendation(
                    location=location,
                    priority="high",
                    recommendation_type="pedestrian_flow",
                    title=f"Protect pedestrian movement around {location}",
                    action="Add temporary pedestrian signage and rerouting around disrupted roads.",
                    reasoning=[
                        "Road disruption may restrict movement.",
                        "Footfall signal indicates elevated pedestrian demand.",
                    ],
                    predicted_outcome={
                        "pedestrian_delay_reduction": "8-15%",
                    },
                    source_events=road_events + footfall_events,
                )
            )

        if city_event_pressure and transport_events:
            recommendations.append(
                make_recommendation(
                    location=location,
                    priority="medium",
                    recommendation_type="event_operations",
                    title=f"Adjust event logistics around {location}",
                    action="Coordinate event timing, station messaging, and crowd flow routes.",
                    reasoning=[
                        "City event pressure is expected.",
                        "Transport disruption risk may affect arrivals and departures.",
                    ],
                    predicted_outcome={
                        "crowding_risk_reduction": "medium",
                    },
                    source_events=city_event_pressure + transport_events,
                )
            )

        if planning_events and road_events:
            recommendations.append(
                make_recommendation(
                    location=location,
                    priority="medium",
                    recommendation_type="roadwork_scheduling",
                    title=f"Review infrastructure scheduling near {location}",
                    action="Avoid scheduling additional works during active road disruption periods.",
                    reasoning=[
                        "Planning or infrastructure activity is present.",
                        "Road disruption is already active nearby.",
                    ],
                    predicted_outcome={
                        "disruption_reduction": "medium",
                    },
                    source_events=planning_events + road_events,
                )
            )

        if weather_events and road_events:
            recommendations.append(
                make_recommendation(
                    location=location,
                    priority="medium",
                    recommendation_type="weather_response",
                    title=f"Prepare weather-aware disruption response near {location}",
                    action="Increase monitoring and prepare wet-weather traffic and pedestrian measures.",
                    reasoning=[
                        "Weather risk may amplify road disruption.",
                        "Rain or wind can increase taxi demand and pedestrian delays.",
                    ],
                    predicted_outcome={
                        "incident_response_improvement": "medium",
                    },
                    source_events=weather_events + road_events,
                )
            )

        if len(location_events) >= 6:
            recommendations.append(
                make_recommendation(
                    location=location,
                    priority="high",
                    recommendation_type="operations_priority",
                    title=f"Prioritise {location} for operations monitoring",
                    action="Flag this location as a priority zone for the operations dashboard.",
                    reasoning=[
                        f"{len(location_events)} operational signals were detected.",
                        "Multiple signals suggest elevated disruption risk.",
                    ],
                    predicted_outcome={
                        "situational_awareness": "high",
                    },
                    source_events=location_events,
                )
            )

    return recommendations


def save_recommendations(recommendations):
    output = {
        "generated_at": now_iso(),
        "source_agent": "agent_4_recommendation",
        "recommendation_count": len(recommendations),
        "recommendations": recommendations,
    }

    path = OUTPUT_DIR / "recommendations.json"
    path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    return path


def run_once():
    print("Urban Pulse Agent 4 starting...")

    events = load_events()
    print(f"Loaded {len(events)} events")

    recommendations = generate_recommendations(events)
    print(f"Generated {len(recommendations)} recommendations")

    path = save_recommendations(recommendations)
    print(f"Saved recommendations to {path}")

    return recommendations


if __name__ == "__main__":
    run_once()


#lol