"""Nemotron-powered recommendation source for Agent 4.

Agent 4's rule engine guarantees coverage and never hallucinates; this module adds
the *intelligence*: it grounds local Nemotron in the relationships Agent 2 actually
discovered and returns explained recommendations in Agent 4's own dict shape, so they
merge straight into the existing list alongside the rule-based and forecast ones.

If Nemotron is unreachable it returns [] - Agent 4 keeps running on rules + forecast.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root on path

from agents.agent2_relationship_discovery.agent2 import run_agent2
from llm.nemotron_client import reason, health

# Agent 2 tags these edges as *discovered* (non-obvious), unlike its structural edges.
DISCOVERED_RELATIONSHIPS = {"positive_correlation", "inverse_correlation", "temporal_proximity"}

SYSTEM_PROMPT = (
    "You are a senior City of London operations analyst. You are given relationships that an "
    "analytics engine has already discovered between urban signals, plus a sample of recent "
    "events. Recommend concrete operational actions a city planner could take tomorrow. "
    "Rules: base every recommendation ONLY on the relationships and events provided - do not "
    "invent data. Prefer non-obvious, specific insights over generic advice. For each "
    "recommendation cite the relationship or event it rests on, and state the predicted outcome."
)

# Schema aligned to Agent 4's own recommendation fields so mapping is near 1:1.
SCHEMA_HINT = (
    'Return JSON of exactly this form: {"recommendations": [{'
    '"title": str, "priority": "high"|"medium"|"low", '
    '"location": str (a location id like "camden_high_street"), '
    '"recommendation_type": str (a short slug like "congestion_mitigation"), '
    '"action": str (the concrete action to take), '
    '"reasoning": [str] (short reasons), '
    '"predicted_outcome": str (one line), '
    '"evidence": str (which discovered relationship or event this rests on)}]}'
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(text) -> str:
    return str(text).strip().lower().replace(" ", "_")


def _graph_records(events: Iterable[Mapping]) -> list[dict]:
    """Agent 4 events store the location id under 'location'; Agent 2 needs 'location_id'."""
    records = []
    for e in events:
        records.append(
            {
                "event_id": e.get("event_id") or e.get("id"),
                "event_type": e.get("event_type"),
                "location_id": e.get("location_id") or e.get("location"),
                "start_time": e.get("start_time"),
                "impact_score": e.get("impact_score", 0.0),
                "duration_minutes": e.get("duration_minutes", 0),
                "confidence": e.get("confidence", 0.7),
            }
        )
    return records


def _top_discovered_edges(graph: dict, limit: int = 12) -> list[dict]:
    edges = [e for e in graph.get("edges", []) if e.get("relationship") in DISCOVERED_RELATIONSHIPS]
    return sorted(edges, key=lambda e: abs(float(e.get("weight", 0))), reverse=True)[:limit]


def build_briefing(graph: dict, events: Iterable[Mapping], max_events: int = 15) -> str:
    """Turn the graph + events into a compact, grounded briefing for Nemotron."""
    lines: list[str] = ["DISCOVERED RELATIONSHIPS (from graph analysis):"]

    discovered = _top_discovered_edges(graph)
    if discovered:
        for e in discovered:
            lines.append(
                f"- {e['relationship']} between {e['source']} and {e['target']} "
                f"(weight {float(e['weight']):.2f}, confidence {float(e['confidence']):.2f}): {e['evidence']}"
            )
    else:
        lines.append("- none yet (not enough events across time/locations to correlate)")

    insights = graph.get("insights", [])
    if insights:
        lines.append("")
        lines.append("HIGH-INFLUENCE NODES:")
        for ins in insights[:6]:
            lines.append(f"- {ins['node_id']} (influence {ins['score']})")

    event_list = list(events)[:max_events]
    if event_list:
        lines.append("")
        lines.append("RECENT EVENTS (sample):")
        for ev in event_list:
            etype = ev.get("event_type", "?")
            loc = ev.get("location_id") or ev.get("location", "?")
            impact = ev.get("impact_score", "?")
            summary = ev.get("summary") or ev.get("description") or ""
            lines.append(f"- [{etype} @ {loc}, impact {impact}] {summary}")

    meta = graph.get("metadata", {})
    lines.append("")
    lines.append(
        f"CONTEXT: {meta.get('event_count', 0)} events analysed, "
        f"{meta.get('edge_count', 0)} relationships in the graph."
    )
    return "\n".join(lines)


def _to_agent4_shape(rec: Mapping) -> dict:
    """Map one Nemotron recommendation into Agent 4's recommendation dict shape."""
    location = rec.get("location") or (rec.get("affected_locations") or ["unknown"])[0]
    rtype = rec.get("recommendation_type") or "nemotron_insight"

    reasoning = rec.get("reasoning")
    if isinstance(reasoning, str):
        reasoning = [reasoning]

    predicted = {"summary": rec.get("predicted_outcome", "")}
    if rec.get("evidence"):
        predicted["evidence"] = rec["evidence"]

    return {
        "id": f"rec_nemotron_{_slug(location)}_{_slug(rtype)}",
        "source_agent": "agent_4_recommendation",
        "timestamp": now_iso(),
        "location": location,
        "priority": rec.get("priority", "medium"),
        "recommendation_type": rtype,
        "title": rec.get("title", "Nemotron recommendation"),
        "action": rec.get("action", ""),
        "reasoning": reasoning or [],
        "predicted_outcome": predicted,
        "source_event_ids": [],
        "generated_by": "nemotron",
    }


def _fallback_text(events: list[Mapping], graph: dict) -> str:
    event = events[0] if events else {}
    location = event.get("location") or event.get("location_id") or "City of London"
    event_type = event.get("event_type", "city signal")
    edge_count = graph.get("metadata", {}).get("edge_count", 0)
    summary = event.get("summary") or event.get("description") or f"{event_type} detected at {location}"

    return (
        f"Title: Prioritise monitoring around {location}\n"
        f"Location: {location}\n"
        "Priority: medium\n"
        f"Action: Review live operations around {location}, because the current event context includes {event_type} "
        "and the relationship graph can amplify impacts across nearby signals.\n"
        "Reasoning:\n"
        f"- Recent event evidence: {summary}\n"
        f"- Agent 2 produced {edge_count} relationship edges for this context.\n"
        "Predicted outcome: Earlier intervention should reduce congestion and crowding escalation."
    )


def generate_nemotron_recommendations(events: Iterable[Mapping], **chat_kwargs) -> list[dict]:
    """Grounded Nemotron recommendations in Agent 4's format. Returns [] if Nemotron is down."""
    events = list(events)

    if not health():
        print("Nemotron unreachable - skipping Nemotron recommendations (rules/forecast still run).")
        return []

    try:
        graph = run_agent2(_graph_records(events))
        briefing = build_briefing(graph, events)

        prompt = f"""
Use the evidence below to produce ONE concrete city operations recommendation.

Do not invent facts.
Base the recommendation only on the discovered relationships and recent events.
Keep it concise.

Return the answer in this structure:

Title: ...
Location: ...
Priority: high/medium/low
Action: ...
Reasoning:
- ...
- ...
Predicted outcome: ...

Evidence:
{briefing}
"""

        text = reason(
            SYSTEM_PROMPT,
            prompt,
            temperature=0.2,
            top_p=0.8,
            max_tokens=500,
        ).strip()

        if not text:
            text = reason(
                "You are a concise city operations analyst. Always return non-empty plain text.",
                f"Write one practical city operations recommendation from this evidence:\n{briefing[:2500]}",
                temperature=0.1,
                top_p=0.9,
                max_tokens=220,
            ).strip()

        if not text:
            print(
                "Nemotron returned empty text twice. "
                "Agent 4 is returning a local evidence-backed fallback recommendation instead."
            )
            text = _fallback_text(events, graph)

        return [
            {
                "id": "rec_nemotron_city_operations",
                "source_agent": "agent_4_recommendation",
                "timestamp": now_iso(),
                "location": "City of London",
                "priority": "medium",
                "recommendation_type": "nemotron_grounded_reasoning",
                "title": "Nemotron-generated operations insight",
                "action": text,
                "reasoning": [
                    "Generated by local NVIDIA Nemotron.",
                    "Grounded in Agent 2 relationship graph and recent city events.",
                ],
                "predicted_outcome": {
                    "summary": "Provides an explainable operational recommendation based on discovered relationships.",
                },
                "source_event_ids": [],
                "generated_by": "nemotron",
            }
        ]

    except Exception as error:
        print(f"Nemotron recommendations failed: {error}")
        return []
