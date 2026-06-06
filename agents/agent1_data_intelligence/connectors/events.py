from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import requests


ECONOMIC_FORECAST_PAGE = "https://data.london.gov.uk/dataset/medium-term-economic-forecast-e5m70/"
ECONOMIC_FORECAST_URL = (
    "https://data.london.gov.uk/download/e5m70/z5p/"
    "GLA-london-economic-outlook-2025-12.xlsx"
)

PRESSURE_LOCATIONS = [
    "Bank",
    "Liverpool Street",
    "Farringdon",
    "Moorgate",
    "Tower Hill",
]


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _clean_text(value):
    return str(value).strip().replace("\n", " ")


def _sheet_summary(sheet_name, frame):
    cleaned = frame.dropna(how="all").dropna(axis=1, how="all")
    flattened = cleaned.stack().tolist()
    labels = [_clean_text(value) for value in flattened if isinstance(value, str) and _clean_text(value)]
    numeric = pd.to_numeric(pd.Series(flattened), errors="coerce").dropna()

    return {
        "sheet": sheet_name,
        "row_count": int(cleaned.shape[0]),
        "column_count": int(cleaned.shape[1]),
        "numeric_value_count": int(len(numeric)),
        "numeric_abs_mean": float(numeric.abs().mean()) if len(numeric) else 0.0,
        "numeric_abs_max": float(numeric.abs().max()) if len(numeric) else 0.0,
        "sample_labels": labels[:8],
    }


def _is_relevant_sheet(summary):
    text = " ".join([summary["sheet"], *summary["sample_labels"]]).lower()
    return any(
        keyword in text
        for keyword in [
            "forecast",
            "employment",
            "jobs",
            "output",
            "gva",
            "income",
            "expenditure",
            "economy",
        ]
    )


def _pressure_from_summary(summary):
    base = summary["numeric_value_count"] * 120
    magnitude = min(summary["numeric_abs_mean"], 100) * 45
    peak = min(summary["numeric_abs_max"], 100) * 25
    return int(max(1500, min(12000, base + magnitude + peak)))


def _category_from_summary(summary):
    text = " ".join([summary["sheet"], *summary["sample_labels"]]).lower()
    if "employment" in text or "jobs" in text:
        return "employment_forecast_pressure"
    if "expenditure" in text or "income" in text:
        return "consumer_activity_forecast"
    if "output" in text or "gva" in text:
        return "economic_output_forecast"
    return "economic_forecast_pressure"


def _description(summary):
    labels = ", ".join(summary["sample_labels"][:3]) or "economic forecast metrics"
    return (
        f"GLA medium-term economic forecast sheet '{summary['sheet']}' indicates "
        f"future city activity pressure. Labels include: {labels}."
    )


def pull_city_events():
    response = requests.get(ECONOMIC_FORECAST_URL, timeout=45)
    response.raise_for_status()

    workbook = pd.read_excel(
        BytesIO(response.content),
        sheet_name=None,
        header=None,
    )

    timestamp = _now_iso()
    summaries = [
        _sheet_summary(sheet_name, frame)
        for sheet_name, frame in workbook.items()
    ]
    summaries = [
        summary
        for summary in summaries
        if summary["row_count"] > 0 and _is_relevant_sheet(summary)
    ]
    summaries = sorted(
        summaries,
        key=lambda summary: (summary["numeric_value_count"], summary["numeric_abs_max"]),
        reverse=True,
    )[: len(PRESSURE_LOCATIONS)]

    events = []
    for location, summary in zip(PRESSURE_LOCATIONS, summaries):
        events.append(
            {
                "name": f"Forecast activity pressure: {summary['sheet']}",
                "location": location,
                "timestamp": timestamp,
                "expected_attendance": _pressure_from_summary(summary),
                "category": _category_from_summary(summary),
                "description": _description(summary),
                "source_url": ECONOMIC_FORECAST_URL,
                "source_page": ECONOMIC_FORECAST_PAGE,
                "data_source": "London Datastore - Medium Term Economic Forecast",
                "summary": summary,
            }
        )

    return events
