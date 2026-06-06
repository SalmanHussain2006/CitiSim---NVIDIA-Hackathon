"""Agent 2: Relationship Discovery Engine.

This agent turns fused city events into a graph of operational relationships:
which locations host which signals, which signals move together over time, and
which disruptions are close enough in time to suggest cascading impact.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable, Mapping

from agents.agent2_relationship_discovery.graph_builder import build_relationship_graph
from gpu.cudf_pipeline import dataframe_backend, dataframe_from_records, load_events


DEMO_EVENTS = [
    {
        "event_id": "demo-roadworks-001",
        "event_type": "roadworks",
        "location_id": "camden_high_street",
        "start_time": "2026-06-07T08:00:00Z",
        "impact_score": 0.82,
        "duration_minutes": 180,
        "confidence": 0.88,
    },
    {
        "event_id": "demo-congestion-001",
        "event_type": "congestion",
        "location_id": "camden_high_street",
        "start_time": "2026-06-07T08:30:00Z",
        "impact_score": 0.76,
        "duration_minutes": 90,
        "confidence": 0.82,
    },
    {
        "event_id": "demo-air-001",
        "event_type": "air_quality_drop",
        "location_id": "camden_high_street",
        "start_time": "2026-06-07T09:00:00Z",
        "impact_score": 0.61,
        "duration_minutes": 120,
        "confidence": 0.74,
    },
    {
        "event_id": "demo-roadworks-002",
        "event_type": "roadworks",
        "location_id": "camden_high_street",
        "start_time": "2026-06-08T08:00:00Z",
        "impact_score": 0.72,
        "duration_minutes": 160,
        "confidence": 0.86,
    },
    {
        "event_id": "demo-congestion-002",
        "event_type": "congestion",
        "location_id": "camden_high_street",
        "start_time": "2026-06-08T08:20:00Z",
        "impact_score": 0.69,
        "duration_minutes": 80,
        "confidence": 0.81,
    },
    {
        "event_id": "demo-air-002",
        "event_type": "air_quality_drop",
        "location_id": "camden_high_street",
        "start_time": "2026-06-08T09:10:00Z",
        "impact_score": 0.58,
        "duration_minutes": 120,
        "confidence": 0.73,
    },
    {
        "event_id": "demo-weather-001",
        "event_type": "heavy_rain",
        "location_id": "kings_cross",
        "start_time": "2026-06-07T08:15:00Z",
        "impact_score": 0.67,
        "duration_minutes": 75,
        "confidence": 0.8,
    },
    {
        "event_id": "demo-cycle-001",
        "event_type": "cycle_demand_drop",
        "location_id": "kings_cross",
        "start_time": "2026-06-07T09:00:00Z",
        "impact_score": 0.55,
        "duration_minutes": 60,
        "confidence": 0.71,
    },
    {
        "event_id": "demo-footfall-001",
        "event_type": "footfall_spike",
        "location_id": "oxford_circus",
        "start_time": "2026-06-07T18:00:00Z",
        "impact_score": 0.79,
        "duration_minutes": 150,
        "confidence": 0.86,
    },
    {
        "event_id": "demo-tube-001",
        "event_type": "station_disruption",
        "location_id": "oxford_circus",
        "start_time": "2026-06-07T18:20:00Z",
        "impact_score": 0.9,
        "duration_minutes": 110,
        "confidence": 0.84,
    },
]


def run_agent2(records: Iterable[Mapping] | None = None, **graph_options) -> dict:
    """Run relationship discovery and return a JSON-serializable payload."""

    frame = dataframe_from_records(DEMO_EVENTS if records is None else records)
    graph = build_relationship_graph(frame, **graph_options)
    payload = asdict(graph)
    payload["metadata"]["dataframe_backend"] = dataframe_backend()
    return payload


def _load_input(path: str | None):
    if path is None:
        return dataframe_from_records(DEMO_EVENTS)
    return load_events(path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Urban Pulse Agent 2 relationship discovery")
    parser.add_argument("--input", help="CSV/JSON/JSONL event dataset. Uses demo events when omitted.")
    parser.add_argument("--output", help="Optional path to write the relationship graph JSON.")
    parser.add_argument("--frequency", default="h", help="Time bucket frequency for correlation discovery.")
    parser.add_argument("--correlation-threshold", type=float, default=0.55)
    parser.add_argument("--temporal-window-minutes", type=int, default=120)
    parser.add_argument("--max-relationship-edges", type=int, default=40)
    parser.add_argument("--min-active-buckets", type=int, default=2)
    return parser


def main() -> None:
    args = _parser().parse_args()
    frame = _load_input(args.input)
    graph = build_relationship_graph(
        frame,
        frequency=args.frequency,
        correlation_threshold=args.correlation_threshold,
        temporal_window_minutes=args.temporal_window_minutes,
        max_relationship_edges=args.max_relationship_edges,
        min_active_buckets=args.min_active_buckets,
    )
    payload = asdict(graph)
    payload["metadata"]["dataframe_backend"] = dataframe_backend()
    text = json.dumps(payload, indent=2)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
