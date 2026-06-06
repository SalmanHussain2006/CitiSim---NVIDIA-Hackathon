"""Relationship discovery graph for Urban Pulse Agent 2."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import combinations
from typing import Iterable, Mapping

import numpy as np
import pandas as pd

from gpu.cudf_pipeline import aggregate_signal_matrix, normalize_events
from gpu.cugraph_utils import degree_centrality, graph_backend


@dataclass(frozen=True)
class RelationshipEdge:
    source: str
    target: str
    relationship: str
    weight: float
    confidence: float
    evidence: str


@dataclass(frozen=True)
class RelationshipGraph:
    nodes: list[dict]
    edges: list[dict]
    insights: list[dict]
    metadata: dict


def _node(node_id: str, node_type: str, label: str, **properties) -> dict:
    return {
        "id": node_id,
        "type": node_type,
        "label": label,
        "properties": properties,
    }


def _signal_label(signal_id: str) -> str:
    location_id, event_type = signal_id.split("::", 1)
    return f"{event_type.replace('_', ' ')} at {location_id}"


def _build_nodes(events: pd.DataFrame, signal_ids: Iterable[str]) -> list[dict]:
    nodes = []
    for location_id in sorted(events["location_id"].unique()):
        nodes.append(_node(f"location:{location_id}", "location", location_id))

    for event_type in sorted(events["event_type"].unique()):
        nodes.append(_node(f"event_type:{event_type}", "event_type", event_type.replace("_", " ")))

    for signal_id in sorted(signal_ids):
        location_id, event_type = signal_id.split("::", 1)
        nodes.append(
            _node(
                f"signal:{signal_id}",
                "urban_signal",
                _signal_label(signal_id),
                location_id=location_id,
                event_type=event_type,
            )
        )
    return nodes


def _structural_edges(events: pd.DataFrame, signal_ids: Iterable[str]) -> list[RelationshipEdge]:
    edges: list[RelationshipEdge] = []
    for signal_id in sorted(signal_ids):
        location_id, event_type = signal_id.split("::", 1)
        rows = events[(events["location_id"] == location_id) & (events["event_type"] == event_type)]
        confidence = float(rows["confidence"].mean()) if not rows.empty else 0.7
        total_impact = float(rows["impact_score"].sum()) if not rows.empty else 0.0
        evidence = f"{len(rows)} events, cumulative impact {total_impact:.2f}"
        edges.append(
            RelationshipEdge(
                source=f"location:{location_id}",
                target=f"signal:{signal_id}",
                relationship="hosts_signal",
                weight=max(total_impact, 0.1),
                confidence=confidence,
                evidence=evidence,
            )
        )
        edges.append(
            RelationshipEdge(
                source=f"event_type:{event_type}",
                target=f"signal:{signal_id}",
                relationship="expressed_as_signal",
                weight=max(total_impact, 0.1),
                confidence=confidence,
                evidence=evidence,
            )
        )
    return edges


def _correlation_edges(
    matrix: pd.DataFrame,
    threshold: float,
    max_edges: int,
    min_active_buckets: int,
) -> list[RelationshipEdge]:
    if matrix.empty or len(matrix.columns) < 2:
        return []

    corr = matrix.corr(method="pearson").replace([np.inf, -np.inf], np.nan).fillna(0.0)
    candidates: list[RelationshipEdge] = []
    for left, right in combinations(corr.columns, 2):
        active_together = int(((matrix[left] > 0) & (matrix[right] > 0)).sum())
        if active_together < min_active_buckets:
            continue
        score = float(corr.loc[left, right])
        if abs(score) < threshold:
            continue
        relationship = "positive_correlation" if score > 0 else "inverse_correlation"
        evidence = (
            f"Pearson r={score:.2f} across {len(matrix.index)} time buckets; "
            f"{active_together} active together"
        )
        candidates.append(
            RelationshipEdge(
                source=f"signal:{left}",
                target=f"signal:{right}",
                relationship=relationship,
                weight=score,
                confidence=min(0.95, 0.45 + abs(score) / 2),
                evidence=evidence,
            )
        )

    return sorted(candidates, key=lambda edge: abs(edge.weight), reverse=True)[:max_edges]


def _near_time_edges(events: pd.DataFrame, window_minutes: int, max_edges: int) -> list[RelationshipEdge]:
    if len(events) < 2:
        return []

    candidates: list[RelationshipEdge] = []
    ordered = events.sort_values("start_time").reset_index(drop=True)
    window = pd.Timedelta(minutes=window_minutes)

    for index, left in ordered.iterrows():
        following = ordered.iloc[index + 1 :]
        following = following[following["start_time"] - left["start_time"] <= window]
        for _, right in following.iterrows():
            if left["location_id"] == right["location_id"] and left["event_type"] == right["event_type"]:
                continue
            minutes = (right["start_time"] - left["start_time"]).total_seconds() / 60
            proximity = max(0.0, 1.0 - (minutes / max(window_minutes, 1)))
            if proximity <= 0:
                continue
            source = f"signal:{left['location_id']}::{left['event_type']}"
            target = f"signal:{right['location_id']}::{right['event_type']}"
            evidence = f"Observed {minutes:.0f} minutes apart"
            candidates.append(
                RelationshipEdge(
                    source=source,
                    target=target,
                    relationship="temporal_proximity",
                    weight=round(proximity, 4),
                    confidence=min(0.9, 0.4 + proximity / 2),
                    evidence=evidence,
                )
            )

    return sorted(candidates, key=lambda edge: edge.weight, reverse=True)[:max_edges]


def _insights(edges: list[dict], limit: int = 5) -> list[dict]:
    centrality = degree_centrality(edges)
    ranked = sorted(centrality.items(), key=lambda item: item[1], reverse=True)[:limit]
    insights = []
    for node_id, score in ranked:
        insights.append(
            {
                "node_id": node_id,
                "score": round(float(score), 4),
                "summary": f"{node_id} is a high-influence node in the discovered city-impact graph.",
            }
        )
    return insights


def build_relationship_graph(
    records: Iterable[Mapping] | pd.DataFrame,
    *,
    frequency: str = "h",
    correlation_threshold: float = 0.55,
    temporal_window_minutes: int = 120,
    max_relationship_edges: int = 40,
    min_active_buckets: int = 2,
) -> RelationshipGraph:
    """Build a relationship graph from fused city event records."""

    events = normalize_events(records)
    matrix = aggregate_signal_matrix(events, frequency=frequency)
    signal_ids = list(matrix.columns)
    if not signal_ids and not events.empty:
        signal_ids = sorted((events["location_id"] + "::" + events["event_type"]).unique())

    edge_objects = (
        _structural_edges(events, signal_ids)
        + _correlation_edges(matrix, correlation_threshold, max_relationship_edges, min_active_buckets)
        + _near_time_edges(events, temporal_window_minutes, max_relationship_edges)
    )
    edges = [asdict(edge) for edge in edge_objects]
    nodes = _build_nodes(events, signal_ids)

    metadata = {
        "agent": "agent2_relationship_discovery",
        "event_count": int(len(events)),
        "node_count": int(len(nodes)),
        "edge_count": int(len(edges)),
        "dataframe_backend": "cudf-compatible",
        "graph_backend": graph_backend(),
        "frequency": frequency,
        "correlation_threshold": correlation_threshold,
        "temporal_window_minutes": temporal_window_minutes,
        "min_active_buckets": min_active_buckets,
    }
    return RelationshipGraph(nodes=nodes, edges=edges, insights=_insights(edges), metadata=metadata)
