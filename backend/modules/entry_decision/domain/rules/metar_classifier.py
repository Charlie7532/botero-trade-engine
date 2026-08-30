"""Centralized METAR D1×D2×D3 classifier.

Single source of truth for bin classification across all 11 stations.
Lookup adapters delegate classification here instead of duplicating
~33 identical _classify_d1/d2/d3 methods.

State keys are numeric vectors: "5__3__3" = D1=Bin5, D2=Bin3, D3=Bin3.
Semantic labels live exclusively in each fact store's _documentation.taxonomy
section and are decoded at the interpretation layer, not baked into keys.
"""

from __future__ import annotations

import math
from typing import Optional


def classify_bin(val: float, edges: list[float]) -> int:
    """Classify a raw value into a bin index using ordered edges.

    Args:
        val: The raw indicator value (e.g. VIX=25.3, FG=42).
        edges: Sorted list of N edges producing N+1 bins.

    Returns:
        Integer bin index in [0, len(edges)].
        Returns -1 if val is NaN.
    """
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return -1
    for idx, e in enumerate(edges):
        if val < e:
            return idx
    return len(edges)


def make_state_key(d1: int, d2: int, d3: int) -> str:
    """Build numeric state key from bin indices.

    Examples:
        make_state_key(5, 3, 3) -> "5__3__3"
        make_state_key(0, 0, 4) -> "0__0__4"
    """
    return f"{d1}__{d2}__{d3}"


def decode_state_key(key: str) -> tuple[int, int, int]:
    """Parse numeric state key back to bin indices.

    Examples:
        decode_state_key("5__3__3") -> (5, 3, 3)
    """
    parts = key.split("__")
    return int(parts[0]), int(parts[1]), int(parts[2])


def resolve_label(
    bin_idx: int,
    labels: list[str],
    fallback: str = "UNKNOWN",
) -> str:
    """Translate a bin index to its semantic label.

    Args:
        bin_idx: Integer bin index from classify_bin().
        labels: Ordered label list from taxonomy.d{n}.labels.
        fallback: Returned when bin_idx is out of range or -1 (NaN).
    """
    if bin_idx < 0 or bin_idx >= len(labels):
        return fallback
    return labels[bin_idx]
