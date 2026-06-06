"""GPU-aware tabular helpers for Urban Pulse.

The hackathon pitch calls for RAPIDS cuDF, but local development machines often
will not have a CUDA stack. This module keeps the public surface small and uses
cuDF when available, falling back to pandas with the same column contract.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, Sequence

import pandas as pd

try:  # pragma: no cover - exercised only on RAPIDS-enabled machines.
    import cudf  # type: ignore
except Exception:  # pragma: no cover - the fallback is the common local path.
    cudf = None


REQUIRED_EVENT_COLUMNS = (
    "event_id",
    "event_type",
    "location_id",
    "start_time",
    "impact_score",
)


def has_gpu_dataframe() -> bool:
    """Return True when cuDF is importable in the current runtime."""

    return cudf is not None


def dataframe_backend() -> str:
    """Name the dataframe backend currently used by this module."""

    return "cudf" if has_gpu_dataframe() else "pandas"


def _read_with_pandas(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".json", ".jsonl"}:
        return pd.read_json(path, lines=path.suffix.lower() == ".jsonl")
    return pd.read_csv(path)


def load_events(path: str | Path, prefer_gpu: bool = True):
    """Load an event dataset from CSV/JSON/JSONL.

    The returned object is a cuDF DataFrame when RAPIDS is available and
    requested; otherwise it is a pandas DataFrame.
    """

    source = Path(path)
    if prefer_gpu and cudf is not None:  # pragma: no cover
        if source.suffix.lower() in {".json", ".jsonl"}:
            return cudf.read_json(str(source), lines=source.suffix.lower() == ".jsonl")
        return cudf.read_csv(str(source))
    return _read_with_pandas(source)


def dataframe_from_records(records: Iterable[Mapping], prefer_gpu: bool = True):
    """Create a dataframe from event-like dictionaries."""

    pdf = pd.DataFrame(list(records))
    if prefer_gpu and cudf is not None:  # pragma: no cover
        return cudf.DataFrame.from_pandas(pdf)
    return pdf


def to_pandas(frame) -> pd.DataFrame:
    """Convert a pandas/cuDF-like DataFrame to pandas."""

    if hasattr(frame, "to_pandas"):
        return frame.to_pandas()
    if isinstance(frame, pd.DataFrame):
        return frame
    return pd.DataFrame(frame)


def normalize_events(frame, required_columns: Sequence[str] = REQUIRED_EVENT_COLUMNS) -> pd.DataFrame:
    """Validate and normalize the event records used by downstream agents."""

    events = to_pandas(frame).copy()
    missing = [column for column in required_columns if column not in events.columns]
    if missing:
        raise ValueError(f"Missing required event columns: {', '.join(missing)}")

    events["event_id"] = events["event_id"].astype(str)
    events["event_type"] = events["event_type"].astype(str).str.strip().str.lower()
    events["location_id"] = events["location_id"].astype(str).str.strip()
    events["start_time"] = pd.to_datetime(events["start_time"], errors="coerce", utc=True)
    events["impact_score"] = pd.to_numeric(events["impact_score"], errors="coerce").fillna(0.0)

    if "duration_minutes" in events.columns:
        events["duration_minutes"] = pd.to_numeric(
            events["duration_minutes"], errors="coerce"
        ).fillna(0.0)
    else:
        events["duration_minutes"] = 0.0

    if "confidence" in events.columns:
        events["confidence"] = pd.to_numeric(events["confidence"], errors="coerce").clip(0, 1)
    else:
        events["confidence"] = 0.7

    events = events.dropna(subset=["start_time"])
    return events.sort_values("start_time").reset_index(drop=True)


def aggregate_signal_matrix(frame, frequency: str = "h") -> pd.DataFrame:
    """Create a time/location/event-type impact matrix for correlation search."""

    events = normalize_events(frame)
    if events.empty:
        return pd.DataFrame()

    events["time_bucket"] = events["start_time"].dt.floor(frequency)
    grouped = (
        events.groupby(["time_bucket", "location_id", "event_type"], as_index=False)
        .agg(
            impact_score=("impact_score", "sum"),
            confidence=("confidence", "mean"),
            event_count=("event_id", "count"),
        )
    )
    grouped["signal_id"] = grouped["location_id"] + "::" + grouped["event_type"]
    return grouped.pivot_table(
        index="time_bucket",
        columns="signal_id",
        values="impact_score",
        aggfunc="sum",
        fill_value=0.0,
    )
