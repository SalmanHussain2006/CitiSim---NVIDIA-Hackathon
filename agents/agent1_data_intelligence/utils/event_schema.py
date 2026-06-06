import uuid
from datetime import datetime, timezone


def now_iso():
    return datetime.now(timezone.utc).isoformat()


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
    return {
        "id": f"evt_{uuid.uuid4().hex[:10]}",
        "source_agent": source_agent,
        "event_type": event_type,
        "timestamp": now_iso(),
        "location": location,
        "coordinates": coordinates,
        "severity": severity,
        "confidence": confidence,
        "summary": summary,
        "data": data,
        "processed_by": [],
    }