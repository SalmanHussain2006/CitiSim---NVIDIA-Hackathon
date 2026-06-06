import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE))

from storage import init_db, recent_events
from agents.agent3_forecast_simulation.agent3 import run_agent3
from agents.agent4_recommendation.agent4_nemotron import generate_nemotron_recommendations
EVENT_DIR = BASE / "data" / "events"
OUTPUT_DIR = BASE / "data" / "recommendations"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def score_to_severity(score):
    try:
        score = float(score)
    except Exception:
        return "medium"

    if score >= 0.85:
        return "high"
    if score >= 0.55:
        return "medium"
    return "low"


def db_row_to_agent4_event(row):
    event_id = row.get("event_id")

    return {
        "id": event_id,
        "event_id": event_id,
        "event_type": row.get("event_type", "unknown"),
        "location": row.get("location_id", "Unknown"),
        "severity": score_to_severity(row.get("impact_score")),
        "confidence": row.get("confidence", 0.7),
        "summary": f"{row.get('event_type', 'unknown')} detected at {row.get('location_id', 'Unknown')}",
        "start_time": str(row.get("start_time")),
        "duration_minutes": row.get("duration_minutes", 60),
        "impact_score": row.get("impact_score", 0.55),
    }


def load_latest_agent1_batch():
    batch_files = sorted(
        EVENT_DIR.glob("agent1_events_*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if not batch_files:
        return []

    latest_file = batch_files[0]
    print(f"Fallback: using latest Agent 1 batch: {latest_file.name}")

    try:
        return json.loads(latest_file.read_text(encoding="utf-8"))
    except Exception as error:
        print(f"Failed to load latest event batch: {error}")
        return []


def load_events(limit=500):
    try:
        conn = init_db()
        try:
            rows = recent_events(conn, limit=limit)
        finally:
            conn.close()

        events = [db_row_to_agent4_event(row) for row in rows]
        print(f"Loaded {len(events)} events from Postgres")
        return events

    except Exception as error:
        print(f"Postgres load failed: {error}")
        return load_latest_agent1_batch()


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
        "source_event_ids": [e.get("id") or e.get("event_id") for e in source_events],    
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

def generate_forecast_recommendations(forecast_payload):
    recommendations = []
    seen = set()

    for alert in forecast_payload.get("alerts", []):
        location_id = alert.get("location_id", "unknown")
        outcome = alert.get("outcome", "risk")
        risk_score = alert.get("risk_score", 0)
        risk_level = alert.get("risk_level", "medium")

        key = (location_id, outcome)
        if key in seen:
            continue
        seen.add(key)

        location = location_id.replace("_", " ").title()

        recommendations.append(
            {
                "id": f"rec_forecast_{location_id}_{outcome}",
                "source_agent": "agent_4_recommendation",
                "timestamp": now_iso(),
                "location": location,
                "priority": "high" if risk_level == "high" else "medium",
                "recommendation_type": f"forecast_{outcome}",
                "title": f"Forecasted {outcome.replace('_', ' ')} risk near {location}",
                "action": "Prioritise this location for operational monitoring and prepare mitigation measures.",
                "reasoning": [
                    f"Agent 3 forecasted a {risk_level} {outcome.replace('_', ' ')} risk.",
                    f"Forecast risk score: {risk_score}",
                    "This recommendation is based on simulated future impact, not only current events.",
                ],
                "predicted_outcome": {
                    "forecast_risk_score": risk_score,
                    "forecast_risk_level": risk_level,
                    "forecast_time": alert.get("time"),
                },
                "source_event_ids": [],
            }
        )

        if len(recommendations) >= 8:
            break

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
    print(f"Generated {len(recommendations)} rule-based recommendations")

    try:
        forecast_payload = run_agent3(
            records=events,
            horizon_hours=6,
            scenario="baseline",
        )

        forecast_recommendations = generate_forecast_recommendations(forecast_payload)
        recommendations.extend(forecast_recommendations)

        print(f"Generated {len(forecast_recommendations)} forecast-based recommendations from Agent 3")

    except Exception as error:
        print(f"Agent 3 forecast recommendations failed: {error}")

    nemotron_recommendations = generate_nemotron_recommendations(events)
    recommendations.extend(nemotron_recommendations)
    print(f"Generated {len(nemotron_recommendations)} Nemotron recommendations")

    print(f"Generated {len(recommendations)} total recommendations")

    path = save_recommendations(recommendations)
    print(f"Saved recommendations to {path}")

    return recommendations


if __name__ == "__main__":
    run_once()