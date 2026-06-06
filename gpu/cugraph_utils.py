"""Graph utilities with optional cuGraph acceleration."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping

import pandas as pd

try:  # pragma: no cover - depends on RAPIDS being installed.
    import cudf  # type: ignore
    import cugraph  # type: ignore
except Exception:  # pragma: no cover - local fallback path.
    cudf = None
    cugraph = None


def has_gpu_graph() -> bool:
    """Return True when cuGraph is importable in the current runtime."""

    return cugraph is not None and cudf is not None


def graph_backend() -> str:
    return "cugraph" if has_gpu_graph() else "python"


def degree_centrality(edges: Iterable[Mapping]) -> dict[str, float]:
    """Compute weighted degree centrality for a relationship edge list."""

    edge_rows = list(edges)
    if not edge_rows:
        return {}

    if has_gpu_graph():  # pragma: no cover
        gdf = cudf.DataFrame(edge_rows)
        graph = cugraph.Graph(directed=True)
        graph.from_cudf_edgelist(
            gdf,
            source="source",
            destination="target",
            edge_attr="weight",
            renumber=False,
        )
        degree_df = cugraph.degree(graph).to_pandas()
        return {
            str(row["vertex"]): float(row["degree"])
            for _, row in degree_df.iterrows()
        }

    scores: defaultdict[str, float] = defaultdict(float)
    for edge in edge_rows:
        weight = abs(float(edge.get("weight", 1.0)))
        scores[str(edge["source"])] += weight
        scores[str(edge["target"])] += weight
    return dict(scores)


def edges_to_dataframe(edges: Iterable[Mapping]) -> pd.DataFrame:
    """Return a stable tabular edge representation for APIs and demos."""

    columns = ["source", "target", "relationship", "weight", "confidence", "evidence"]
    return pd.DataFrame(list(edges), columns=columns)
