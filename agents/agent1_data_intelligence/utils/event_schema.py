import uuid
from datetime import datetime, timezone


SEVERITY_IMPACT = {
    "low": 0.25,
    "medium": 0.6,
    "high": 0.85,
    "critical": 1.0,
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def location_to_id(location):
    return str(location).strip().lower().replace(" ", "_")


def severity_to_impact(severity):
    return SEVERITY_IMPACT.get(str(severity).strip().lower(), 0.5)


def create_event(
    event_type,
    location,
    coordinates,
    severity,
    summary,
    data,
    confidence=0.8,
    source_agent="agent_1_data_intelligence",
):
    event_id = f"evt_{uuid.uuid4().hex[:10]}"
    timestamp = now_iso()

    return {
        "id": event_id,
        "event_id": event_id,
        "source_agent": source_agent,
        "event_type": event_type,
        "timestamp": timestamp,
        "start_time": timestamp,
        "location": location,
        "location_id": location_to_id(location),
        "coordinates": coordinates,
        "severity": severity,
        "impact_score": severity_to_impact(severity),
        "confidence": confidence,
        "summary": summary,
        "data": data,
        "processed_by": [],
    }
