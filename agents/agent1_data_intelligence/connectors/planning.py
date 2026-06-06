from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import requests


PLANNING_STATS_URL = (
    "https://data.london.gov.uk/download/248wz/"
    "9c1fe8c7-4510-495e-ac87-e8cacda55910/"
    "planning-and-development-control-statistics.xls"
)


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _clean_value(value):
    if pd.isna(value):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (int, float, str, bool)):
        return value
    return str(value)


def _sheet_summary(name, frame):
    cleaned = frame.dropna(how="all").dropna(axis=1, how="all")
    numeric_values = pd.to_numeric(cleaned.stack(), errors="coerce").dropna()
    text_values = [
        str(value).strip()
        for value in cleaned.stack().tolist()
        if isinstance(value, str) and str(value).strip()
    ]

    return {
        "sheet": name,
        "row_count": int(cleaned.shape[0]),
        "column_count": int(cleaned.shape[1]),
        "numeric_value_count": int(len(numeric_values)),
        "numeric_total": float(numeric_values.sum()) if len(numeric_values) else 0.0,
        "sample_labels": text_values[:8],
    }


def _impact_from_summary(summary):
    numeric_total = summary["numeric_total"]
    if numeric_total >= 10000:
        return "high"
    if numeric_total >= 1000:
        return "medium"
    return "low"


def _summary_description(summary):
    labels = ", ".join(summary["sample_labels"][:3]) or "planning statistics"
    return (
        f"London planning statistics sheet '{summary['sheet']}' was ingested "
        f"({summary['row_count']} rows, labels include: {labels})."
    )


def pull_planning_data():
    response = requests.get(PLANNING_STATS_URL, timeout=45)
    response.raise_for_status()

    workbook = pd.read_excel(
        BytesIO(response.content),
        sheet_name=None,
        header=None,
    )

    timestamp = _now_iso()
    items = []

    for sheet_name, frame in workbook.items():
        summary = _sheet_summary(sheet_name, frame)
        if summary["row_count"] == 0:
            continue

        items.append(
            {
                "location": "City of London",
                "timestamp": timestamp,
                "project_type": "planning_development_control_statistics",
                "impact": _impact_from_summary(summary),
                "description": _summary_description(summary),
                "source_url": PLANNING_STATS_URL,
                "sheet": sheet_name,
                "data_source": "London Datastore",
                "summary": summary,
            }
        )

    return items
