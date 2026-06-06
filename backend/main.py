"""FastAPI backend for the CitiPulse simulation dashboard."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from statistics import mean
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

from agents.agent3_forecast_simulation.agent3 import run_agent3


FRONTEND_DIR = BASE / "frontend"

SCENARIO_PATTERNS = [
    ("roadworks", ("roadworks", "road work", "lane closure", "maintenance", "works")),
    ("heavy_rain", ("rain", "storm", "flood", "weather", "wind")),
    ("office_development", ("office", "development", "construction", "new building", "pedestrianised", "pedestrianized")),
    ("station_disruption", ("station", "tube", "train", "rail", "platform", "underground")),
]

KNOWN_LOCATIONS = {
    "bank": "bank",
    "liverpool street": "liverpool_street",
    "liverpool_street": "liverpool_street",
    "farringdon": "farringdon",
    "moorgate": "moorgate",
    "tower hill": "tower_hill",
    "tower_hill": "tower_hill",
    "oxford circus": "oxford_circus",
    "oxford_circus": "oxford_circus",
    "camden": "camden_high_street",
    "camden high street": "camden_high_street",
    "kings cross": "kings_cross",
    "king's cross": "kings_cross",
    "kings_cross": "kings_cross",
}


class SimulationRequest(BaseModel):
    prompt: str = Field(..., min_length=3)
    horizon_hours: int = Field(default=12, ge=1, le=48)


def _humanize(value: str) -> str:
    return value.replace("_", " ").title()


def parse_prompt(prompt: str) -> dict[str, str]:
    normalized = re.sub(r"\s+", " ", prompt.strip().lower())

    scenario = "baseline"
    for candidate, patterns in SCENARIO_PATTERNS:
        if any(pattern in normalized for pattern in patterns):
            scenario = candidate
            break

    location = "liverpool_street"
    for label, location_id in KNOWN_LOCATIONS.items():
        if label in normalized:
            location = location_id
            break

    return {"scenario": scenario, "location_id": location}


def _risk_label(score: float) -> str:
    if score >= 0.75:
        return "High"
    if score >= 0.45:
        return "Medium"
    return "Low"


def _series_for_location(forecast: list[dict[str, Any]], location_id: str) -> list[dict[str, Any]]:
    rows = [row for row in forecast if row["location_id"] == location_id]
    if not rows and forecast:
        first_location = forecast[0]["location_id"]
        rows = [row for row in forecast if row["location_id"] == first_location]
    return rows


def _headline(parsed: dict[str, str], series: list[dict[str, Any]]) -> dict[str, Any]:
    if not series:
        return {
            "title": "No forecast data available",
            "summary": "Run Agent 1 or provide event records before simulation.",
            "risk_level": "Low",
        }

    peaks = {
        "congestion": max(row["congestion_risk"] for row in series),
        "footfall": max(row["footfall_pressure"] for row in series),
        "air_quality": max(row["air_quality_risk"] for row in series),
        "cycle_demand_drop": max(1 - row["cycle_demand"] for row in series),
    }
    outcome, score = max(peaks.items(), key=lambda item: item[1])
    title = f"{_humanize(parsed['location_id'])}: {_humanize(outcome)} risk is {_risk_label(score).lower()}"
    summary = (
        f"The {parsed['scenario'].replace('_', ' ')} simulation peaks at "
        f"{score:.0%} {outcome.replace('_', ' ')} risk over the forecast horizon."
    )
    return {"title": title, "summary": summary, "risk_level": _risk_label(score), "peak_score": round(score, 4)}


def _recommendations(headline: dict[str, Any], parsed: dict[str, str], alerts: list[dict[str, Any]]) -> list[dict[str, str]]:
    scenario = parsed["scenario"]
    location = _humanize(parsed["location_id"])
    suggestions = []

    if scenario in {"roadworks", "office_development"}:
        suggestions.append(
            {
                "title": "Stage the intervention outside peak periods",
                "action": f"Phase works around {location} and reserve bus/cycle diversion capacity before the morning and evening peaks.",
            }
        )
    if scenario in {"heavy_rain", "station_disruption"}:
        suggestions.append(
            {
                "title": "Increase live operations monitoring",
                "action": f"Put {location} on a watchlist and trigger station, road, and pedestrian updates when risk crosses medium.",
            }
        )

    if alerts:
        top = alerts[0]
        suggestions.append(
            {
                "title": f"Mitigate {top['outcome'].replace('_', ' ')} risk",
                "action": "Deploy temporary signage, routing messages, and traffic control where forecast risk is highest.",
            }
        )

    suggestions.append(
        {
            "title": "Re-run after mitigation",
            "action": "Test a second scenario with reduced impact or shorter duration to compare the before/after forecast.",
        }
    )
    return suggestions[:4]


def build_chart_series(series: list[dict[str, Any]]) -> dict[str, Any]:
    labels = [row["time"][11:16] for row in series]
    return {
        "labels": labels,
        "congestion": [row["congestion_risk"] for row in series],
        "footfall": [row["footfall_pressure"] for row in series],
        "air_quality": [row["air_quality_risk"] for row in series],
        "cycleDemand": [row["cycle_demand"] for row in series],
    }


app = FastAPI(title="CitiPulse")

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "citipulse-backend"}


@app.post("/api/simulate")
def simulate(request: SimulationRequest):
    parsed = parse_prompt(request.prompt)
    payload = run_agent3(
        horizon_hours=request.horizon_hours,
        scenario=parsed["scenario"],
        scenario_location=parsed["location_id"],
    )

    location_series = _series_for_location(payload["forecast"], parsed["location_id"])
    headline = _headline(parsed, location_series)
    alerts = [
        alert for alert in payload["alerts"]
        if alert["location_id"] == parsed["location_id"]
    ] or payload["alerts"][:5]

    return {
        "prompt": request.prompt,
        "scenario": {
            "name": parsed["scenario"],
            "location_id": parsed["location_id"],
            "label": f"{_humanize(parsed['scenario'])} at {_humanize(parsed['location_id'])}",
        },
        "headline": headline,
        "chart": build_chart_series(location_series),
        "forecast": location_series,
        "alerts": alerts[:6],
        "recommendations": _recommendations(headline, parsed, alerts),
        "metadata": payload["metadata"],
        "relationship_summary": payload.get("relationship_summary", {}),
        "averages": {
            "congestion": round(mean([row["congestion_risk"] for row in location_series]), 4) if location_series else 0,
            "footfall": round(mean([row["footfall_pressure"] for row in location_series]), 4) if location_series else 0,
            "air_quality": round(mean([row["air_quality_risk"] for row in location_series]), 4) if location_series else 0,
            "cycle_demand": round(mean([row["cycle_demand"] for row in location_series]), 4) if location_series else 0,
        },
    }
