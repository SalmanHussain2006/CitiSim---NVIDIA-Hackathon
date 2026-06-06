"""
event_schema.py - the single source of truth for what an Urban Pulse event looks like.

Agent 1 produces events through create_event(); Agent 2 (via gpu/cudf_pipeline.py)
reads them. To keep the system connected, the keys here MUST match the contract in
cudf_pipeline.REQUIRED_EVENT_COLUMNS:

    event_id, event_type, location_id, start_time, impact_score      (required)
    duration_minutes, confidence                                     (optional, used if present)

We also carry human-readable fields (summary, coordinates, severity label) and a set
of compatibility aliases (description, value, latitude/longitude, ...) so the same dict
slots into storage whatever its column names are. Extra keys are harmless: a parameterised
INSERT only reads the placeholders it names.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping, Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_location_id(name: str) -> str:
    """'Liverpool Street' -> 'liverpool_street'. This is what Agent 2 groups on."""
    slug = re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_")
    return slug or "unknown"


# Word severities -> numeric impact. Agent 2 sums impact_score for edge weights,
# so this is what makes one event "heavier" than another in the graph.
_SEVERITY_TO_IMPACT = {"high": 0.85, "medium": 0.6, "low": 0.3}


def severity_to_impact(severity: Any) -> float:
    """Accept a word ('high') or an already-numeric score and return a 0-1 float."""
    if isinstance(severity, (int, float)):
        return max(0.0, min(1.0, float(severity)))
    return _SEVERITY_TO_IMPACT.get(str(severity).strip().lower(), 0.5)


# Rough how-long-does-this-last estimates (minutes), since raw feeds rarely say.
_DEFAULT_DURATION = {
    "road_disruption": 180,
    "transport_disruption_risk": 90,
    "weather_congestion_risk": 60,
    "weather_pedestrian_risk": 60,
    "footfall_signal": 120,
    "city_event_pressure": 240,
    "planning_infrastructure_signal": 1440,
    "air_quality_monitoring_available": 60,
    "location_monitoring_snapshot": 5,
}


def estimate_duration(event_type: str) -> int:
    return _DEFAULT_DURATION.get(event_type, 90)


def make_event_id(dedup_key: Optional[str] = None) -> str:
    """
    A STABLE id derived from a natural key (e.g. the TfL disruption id) lets the
    storage upsert refresh the same real-world event instead of duplicating it.
    Without a key we fall back to a random id - fine, but that event can never dedup.
    """
    if dedup_key:
        digest = hashlib.sha1(str(dedup_key).encode("utf-8")).hexdigest()[:12]
        return f"evt_{digest}"
    return f"evt_{uuid.uuid4().hex[:10]}"


def create_event(
    event_type: str,
    location: str,
    coordinates: Mapping[str, Any],
    severity: Any,
    summary: str,
    data: Any,
    confidence: float = 0.8,
    source_agent: str = "agent_1_data_intelligence",
    dedup_key: Optional[str] = None,
    duration_minutes: Optional[int] = None,
    start_time: Optional[str] = None,
) -> dict:
    """Build one canonical event. Same call signature Agent 1 already uses, new output shape."""
    coords = coordinates or {}
    location_id = to_location_id(location)
    when = start_time or now_iso()
    event_id = make_event_id(dedup_key)
    impact_score = severity_to_impact(severity)

    return {
        # ---- canonical contract (what Agent 2 reads) ----
        "id": event_id,
        "event_id": event_id,
        "event_type": str(event_type),
        "location_id": location_id,
        "start_time": when,
        "impact_score": impact_score,
        "duration_minutes": duration_minutes if duration_minutes is not None else estimate_duration(event_type),
        "confidence": float(confidence),

        # ---- human-readable extras ----
        "location": location,
        "coordinates": coords,
        "severity": severity,
        "summary": summary,
        "source_agent": source_agent,
        "data": data,
        "processed_by": [],

        # ---- compatibility aliases ----
        "source": source_agent,
        "category": str(event_type),
        "description": summary,
        "value": impact_score,
        "latitude": coords.get("lat"),
        "longitude": coords.get("lon"),
        "location_name": location,
        "timestamp": when,
        "raw": data,
    }