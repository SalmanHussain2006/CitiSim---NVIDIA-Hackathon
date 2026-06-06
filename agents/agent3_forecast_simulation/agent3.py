"""Agent 3: Forecast and Simulation Engine."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from agents.agent2_relationship_discovery.agent2 import DEMO_EVENTS, run_agent2
from agents.agent3_forecast_simulation.congestion_forecaster import (
    adapt_agent_events,
    build_scenario_events,
    forecast_city_impacts,
)


BASE = Path(__file__).resolve().parents[2]
EVENT_DIR = BASE / "data" / "events"


def _read_json(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    return [data]


def latest_agent1_batch() -> Path | None:
    if not EVENT_DIR.exists():
        return None
    batches = sorted(EVENT_DIR.glob("agent1_events_*.json"), key=lambda path: path.stat().st_mtime)
    return batches[-1] if batches else None


def load_event_records(path: str | None = None):
    if path:
        return _read_json(Path(path))

    latest = latest_agent1_batch()
    if latest:
        return _read_json(latest)

    return DEMO_EVENTS


def run_agent3(
    records=None,
    *,
    horizon_hours: int = 24,
    scenario: str = "baseline",
    scenario_location: str = "liverpool_street",
    relationship_graph: dict | None = None,
) -> dict:
    """Run future impact forecasting from event records."""

    base_records = records if records is not None else load_event_records()
    normalized_records = adapt_agent_events(base_records).to_dict(orient="records")
    relationship_graph = relationship_graph or run_agent2(normalized_records, min_active_buckets=1)

    scenario_events = []
    if scenario != "baseline":
        scenario_events = build_scenario_events(
            scenario,
            scenario_location,
            pd.Timestamp.now(tz="UTC").ceil("h"),
        )

    result = forecast_city_impacts(
        base_records,
        relationship_graph=relationship_graph,
        horizon_hours=horizon_hours,
        scenario_events=scenario_events,
        scenario_name=scenario,
    )
    payload = asdict(result)
    payload["relationship_summary"] = {
        "node_count": relationship_graph.get("metadata", {}).get("node_count"),
        "edge_count": relationship_graph.get("metadata", {}).get("edge_count"),
        "top_insights": relationship_graph.get("insights", [])[:3],
    }
    return payload


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Urban Pulse Agent 3 forecast and simulation")
    parser.add_argument("--input", help="Optional Agent 1 event batch JSON. Uses latest data/events batch when omitted.")
    parser.add_argument("--output", help="Optional path to write forecast JSON.")
    parser.add_argument("--horizon-hours", type=int, default=24)
    parser.add_argument(
        "--scenario",
        default="baseline",
        choices=["baseline", "roadworks", "heavy_rain", "office_development", "station_disruption"],
    )
    parser.add_argument("--scenario-location", default="liverpool_street")
    return parser


def main() -> None:
    args = _parser().parse_args()
    payload = run_agent3(
        load_event_records(args.input),
        horizon_hours=args.horizon_hours,
        scenario=args.scenario,
        scenario_location=args.scenario_location,
    )
    text = json.dumps(payload, indent=2)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
