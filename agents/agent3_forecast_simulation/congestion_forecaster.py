"""Forecasting primitives for Urban Pulse Agent 3.

The hackathon concept asks Agent 3 to predict congestion, footfall, cycle demand
and air-quality outcomes. This module uses deterministic simulation so it works
with the small event volumes available during a demo, while still accepting the
relationship graph produced by Agent 2.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Iterable, Mapping

import pandas as pd

from gpu.cudf_pipeline import normalize_events


SEVERITY_IMPACT = {
    "low": 0.25,
    "medium": 0.6,
    "high": 0.85,
    "critical": 1.0,
}

EVENT_OUTCOME_WEIGHTS = {
    "road_disruption": {"congestion": 0.95, "air_quality": 0.5, "cycle_demand": -0.25},
    "roadworks": {"congestion": 0.9, "air_quality": 0.45, "cycle_demand": -0.2},
    "transport_disruption_risk": {"congestion": 0.75, "footfall": -0.35},
    "station_disruption": {"congestion": 0.85, "footfall": -0.45},
    "weather_congestion_risk": {"congestion": 0.65, "footfall": -0.25, "cycle_demand": -0.55},
    "weather_pedestrian_risk": {"footfall": -0.35, "cycle_demand": -0.65},
    "heavy_rain": {"congestion": 0.7, "footfall": -0.25, "cycle_demand": -0.6},
    "footfall_signal": {"footfall": 0.85, "congestion": 0.35},
    "footfall_spike": {"footfall": 0.9, "congestion": 0.45},
    "city_event_pressure": {"footfall": 0.9, "congestion": 0.55, "air_quality": 0.25},
    "planning_infrastructure_signal": {"congestion": 0.55, "footfall": 0.3, "air_quality": 0.2},
    "air_quality_monitoring_available": {"air_quality": 0.1},
    "air_quality_drop": {"air_quality": 0.85, "congestion": 0.25},
    "cycle_demand_drop": {"cycle_demand": -0.8},
    "location_monitoring_snapshot": {"congestion": 0.05, "footfall": 0.05, "air_quality": 0.05},
}

OUTCOMES = ("congestion", "footfall", "cycle_demand", "air_quality")


@dataclass(frozen=True)
class ForecastPoint:
    time: str
    location_id: str
    congestion_risk: float
    footfall_pressure: float
    cycle_demand: float
    air_quality_risk: float
    confidence: float
    drivers: list[str]


@dataclass(frozen=True)
class ForecastResult:
    forecast: list[dict]
    alerts: list[dict]
    scenario: dict
    metadata: dict


def _slug(value) -> str:
    return str(value).strip().lower().replace(" ", "_")


def _impact_from_severity(value) -> float:
    return SEVERITY_IMPACT.get(str(value).strip().lower(), 0.5)


def adapt_agent_events(records: Iterable[Mapping] | pd.DataFrame) -> pd.DataFrame:
    """Convert Agent 1 or Agent 2 event shapes into Agent 3's forecast schema."""

    frame = records.copy() if isinstance(records, pd.DataFrame) else pd.DataFrame(list(records))
    if frame.empty:
        return pd.DataFrame(
            columns=["event_id", "event_type", "location_id", "start_time", "impact_score", "confidence"]
        )

    if "event_id" not in frame.columns:
        frame["event_id"] = frame.get("id", pd.Series(range(len(frame)))).astype(str)
    if "location_id" not in frame.columns:
        locations = frame["location"] if "location" in frame.columns else pd.Series(["unknown"] * len(frame))
        frame["location_id"] = locations.map(_slug)
    if "start_time" not in frame.columns:
        frame["start_time"] = frame.get("timestamp", pd.Timestamp.utcnow().isoformat())
    if "impact_score" not in frame.columns:
        severities = frame["severity"] if "severity" in frame.columns else pd.Series(["medium"] * len(frame))
        frame["impact_score"] = severities.map(_impact_from_severity)
    if "confidence" not in frame.columns:
        frame["confidence"] = 0.7
    if "event_type" not in frame.columns:
        frame["event_type"] = "unknown_signal"

    return normalize_events(frame)


def _relationship_lookup(relationship_graph: Mapping | None) -> dict[str, list[dict]]:
    lookup: dict[str, list[dict]] = {}
    if not relationship_graph:
        return lookup

    for edge in relationship_graph.get("edges", []):
        source = str(edge.get("source", ""))
        target = str(edge.get("target", ""))
        if not source.startswith("signal:") or not target.startswith("signal:"):
            continue
        if edge.get("relationship") not in {
            "positive_correlation",
            "temporal_proximity",
            "inverse_correlation",
        }:
            continue
        lookup.setdefault(source.removeprefix("signal:"), []).append(edge)
    return lookup


def _future_hours(events: pd.DataFrame, horizon_hours: int) -> list[pd.Timestamp]:
    base = pd.Timestamp.now(tz="UTC")
    if not events.empty:
        latest = events["start_time"].max()
        if pd.notna(latest):
            base = max(base, latest)
    start = base.ceil("h")
    return [start + timedelta(hours=offset) for offset in range(1, horizon_hours + 1)]


def _time_multiplier(hour: int, outcome: str) -> float:
    if outcome == "congestion" and hour in {7, 8, 9, 16, 17, 18}:
        return 1.25
    if outcome == "footfall" and hour in {8, 9, 12, 13, 17, 18, 19}:
        return 1.18
    if outcome == "cycle_demand" and hour in {7, 8, 17, 18}:
        return 1.15
    if outcome == "air_quality" and hour in {8, 9, 17, 18}:
        return 1.16
    return 1.0


def _decay(hours_since_event: float) -> float:
    if hours_since_event < 0:
        return 0.0
    return max(0.08, 1.0 / (1.0 + hours_since_event / 4.0))


def _score_to_level(score: float) -> str:
    if score >= 0.75:
        return "high"
    if score >= 0.45:
        return "medium"
    return "low"


def _empty_scores() -> dict[str, float]:
    return {
        "congestion": 0.08,
        "footfall": 0.08,
        "cycle_demand": 0.55,
        "air_quality": 0.08,
    }


def _apply_event(scores: dict[str, float], event: pd.Series, forecast_time: pd.Timestamp) -> list[str]:
    event_type = str(event["event_type"])
    weights = EVENT_OUTCOME_WEIGHTS.get(event_type, {"congestion": 0.25})
    impact = float(event["impact_score"]) * float(event["confidence"])
    hours_since = (forecast_time - event["start_time"]).total_seconds() / 3600
    strength = impact * _decay(hours_since)
    drivers = []

    for outcome, weight in weights.items():
        delta = strength * abs(weight) * _time_multiplier(forecast_time.hour, outcome)
        if weight < 0:
            scores[outcome] = max(0.0, scores[outcome] - delta)
        else:
            scores[outcome] = min(1.0, scores[outcome] + delta)
        if delta >= 0.08:
            drivers.append(event_type)
    return drivers


def _propagate_relationships(
    scores_by_signal: dict[str, dict[str, float]],
    relationship_graph: Mapping | None,
) -> None:
    lookup = _relationship_lookup(relationship_graph)
    if not lookup:
        return

    for source_signal, edges in lookup.items():
        source_location = source_signal.split("::", 1)[0]
        source_scores = scores_by_signal.get(f"{source_location}::forecast")
        if not source_scores:
            continue
        for edge in edges:
            target_signal = str(edge["target"]).removeprefix("signal:")
            target_location = target_signal.split("::", 1)[0]
            target_key = f"{target_location}::forecast"
            if target_key not in scores_by_signal:
                continue
            multiplier = abs(float(edge.get("weight", 0.0))) * float(edge.get("confidence", 0.7)) * 0.18
            if edge.get("relationship") == "inverse_correlation":
                multiplier *= -1
            for outcome in OUTCOMES:
                delta = source_scores[outcome] * multiplier
                scores_by_signal[target_key][outcome] = min(
                    1.0,
                    max(0.0, scores_by_signal[target_key][outcome] + delta),
                )


def build_scenario_events(scenario: str, location_id: str, start_time: pd.Timestamp) -> list[dict]:
    """Create synthetic future events for what-if simulation."""

    scenario = scenario.strip().lower()
    templates = {
        "roadworks": [
            ("scenario_roadworks", "roadworks", 0.85, 0),
            ("scenario_congestion", "congestion", 0.7, 1),
        ],
        "heavy_rain": [
            ("scenario_rain", "heavy_rain", 0.72, 0),
            ("scenario_cycle_drop", "cycle_demand_drop", 0.55, 1),
        ],
        "office_development": [
            ("scenario_planning", "planning_infrastructure_signal", 0.68, 0),
            ("scenario_footfall", "footfall_spike", 0.62, 2),
        ],
        "station_disruption": [
            ("scenario_station", "station_disruption", 0.88, 0),
            ("scenario_congestion", "congestion", 0.72, 1),
        ],
    }
    rows = []
    for event_id, event_type, impact, offset in templates.get(scenario, []):
        rows.append(
            {
                "event_id": event_id,
                "event_type": event_type,
                "location_id": location_id,
                "start_time": (start_time + timedelta(hours=offset)).isoformat(),
                "impact_score": impact,
                "confidence": 0.82,
            }
        )
    return rows


def forecast_city_impacts(
    records: Iterable[Mapping] | pd.DataFrame,
    *,
    relationship_graph: Mapping | None = None,
    horizon_hours: int = 24,
    scenario_events: Iterable[Mapping] | None = None,
    scenario_name: str = "baseline",
) -> ForecastResult:
    """Predict future city impacts from current events and Agent 2 relationships."""

    events = adapt_agent_events(records)
    if scenario_events:
        events = pd.concat([events, adapt_agent_events(scenario_events)], ignore_index=True)
        events = normalize_events(events)

    hours = _future_hours(events, horizon_hours)
    locations = sorted(events["location_id"].unique()) if not events.empty else ["city_of_london"]
    points: list[ForecastPoint] = []

    for forecast_time in hours:
        scores_by_signal: dict[str, dict[str, float]] = {}
        drivers_by_location: dict[str, set[str]] = {location_id: set() for location_id in locations}

        for location_id in locations:
            scores = _empty_scores()
            location_events = events[events["location_id"] == location_id]
            for _, event in location_events.iterrows():
                for driver in _apply_event(scores, event, forecast_time):
                    drivers_by_location[location_id].add(driver)
            scores_by_signal[f"{location_id}::forecast"] = scores

        _propagate_relationships(scores_by_signal, relationship_graph)

        for location_id in locations:
            scores = scores_by_signal[f"{location_id}::forecast"]
            confidence = min(0.92, 0.45 + float(events[events["location_id"] == location_id]["confidence"].mean() or 0.5) / 2)
            points.append(
                ForecastPoint(
                    time=forecast_time.isoformat(),
                    location_id=location_id,
                    congestion_risk=round(scores["congestion"], 4),
                    footfall_pressure=round(scores["footfall"], 4),
                    cycle_demand=round(scores["cycle_demand"], 4),
                    air_quality_risk=round(scores["air_quality"], 4),
                    confidence=round(confidence, 4),
                    drivers=sorted(drivers_by_location[location_id])[:5],
                )
            )

    forecast = [asdict(point) for point in points]
    alerts = []
    for point in forecast:
        risks = {
            "congestion": point["congestion_risk"],
            "footfall": point["footfall_pressure"],
            "air_quality": point["air_quality_risk"],
            "cycle_demand_drop": 1 - point["cycle_demand"],
        }
        outcome, score = max(risks.items(), key=lambda item: item[1])
        if score >= 0.68:
            alerts.append(
                {
                    "time": point["time"],
                    "location_id": point["location_id"],
                    "outcome": outcome,
                    "risk_score": round(score, 4),
                    "risk_level": _score_to_level(score),
                    "drivers": point["drivers"],
                }
            )

    return ForecastResult(
        forecast=forecast,
        alerts=alerts[:20],
        scenario={
            "name": scenario_name,
            "injected_event_count": len(list(scenario_events or [])),
            "horizon_hours": horizon_hours,
        },
        metadata={
            "agent": "agent3_forecast_simulation",
            "event_count": int(len(events)),
            "location_count": int(len(locations)),
            "forecast_point_count": int(len(forecast)),
            "uses_relationship_graph": bool(relationship_graph),
            "model": "deterministic_event_decay_relationship_simulator",
        },
    )
