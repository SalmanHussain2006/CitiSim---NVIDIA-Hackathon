from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO

import pandas as pd
import requests


WALKING_CYCLING_URL = (
    "https://data.london.gov.uk/download/vd6j4/"
    "c7ae3969-9d32-40ab-8407-589464030231/"
    "Walking-Cycling.csv"
)

LOCATION_BOROUGHS = {
    "Liverpool Street": "City of London",
    "Bank": "City of London",
    "Moorgate": "City of London",
    "Farringdon": "Islington",
    "Tower Hill": "Tower Hamlets",
}


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _normalise_column(value):
    return str(value).strip().lower().replace("\n", " ")


def _find_column(columns, candidates):
    normalised = {_normalise_column(column): column for column in columns}
    for candidate in candidates:
        for normalised_name, original in normalised.items():
            if candidate in normalised_name:
                return original
    return None


def _numeric_series(frame, columns):
    if not columns:
        return pd.Series([0.0] * len(frame), index=frame.index)

    values = []
    for column in columns:
        series = (
            frame[column]
            .astype(str)
            .str.replace("%", "", regex=False)
            .str.replace("-", "0", regex=False)
        )
        values.append(pd.to_numeric(series, errors="coerce"))

    return pd.concat(values, axis=1).mean(axis=1).fillna(0.0)


def _latest_rows(frame, area_column, year_column):
    if year_column is None:
        return frame

    years = pd.to_numeric(frame[year_column], errors="coerce")
    if years.notna().any():
        frame = frame.copy()
        frame["_year_sort"] = years
        return frame.sort_values("_year_sort").groupby(area_column, as_index=False).tail(1)

    return frame


def _active_travel_scores(frame):
    area_column = _find_column(
        frame.columns,
        ["local authority", "borough", "area name", "area"],
    )
    if area_column is None:
        raise ValueError("Walking/cycling CSV does not include a borough or area column.")

    year_column = _find_column(frame.columns, ["year", "date"])
    metric_columns = [
        column
        for column in frame.columns
        if any(term in _normalise_column(column) for term in ["walk", "cycle", "cycling"])
    ]
    metric_columns = [column for column in metric_columns if column != area_column]

    latest = _latest_rows(frame, area_column, year_column).copy()
    latest["active_travel_score"] = _numeric_series(latest, metric_columns)
    return latest, area_column, metric_columns


def pull_footfall():
    response = requests.get(WALKING_CYCLING_URL, timeout=45)
    response.raise_for_status()

    frame = pd.read_csv(StringIO(response.text))
    active_rows, area_column, metric_columns = _active_travel_scores(frame)

    baseline = float(active_rows["active_travel_score"].median() or 1.0)
    timestamp = _now_iso()
    events = []

    for location, borough in LOCATION_BOROUGHS.items():
        borough_rows = active_rows[
            active_rows[area_column].astype(str).str.casefold() == borough.casefold()
        ]
        if borough_rows.empty:
            continue

        row = borough_rows.iloc[0]
        score = float(row["active_travel_score"])
        events.append(
            {
                "location": location,
                "timestamp": timestamp,
                "footfall_count": round(score, 2),
                "baseline": round(baseline, 2),
                "source_url": WALKING_CYCLING_URL,
                "data_source": "London Datastore - Walking and Cycling by Borough",
                "borough": borough,
                "metric_columns": [str(column) for column in metric_columns],
                "note": "Open active-travel borough data used as a pedestrian demand proxy.",
                "raw": row.drop(labels=["active_travel_score"], errors="ignore").to_dict(),
            }
        )

    return events
