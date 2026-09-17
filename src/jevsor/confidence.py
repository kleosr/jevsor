"""jevsor-defined confidence: 1 - H(p)/log(K). Not TypeSafe's unpublished formula."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Literal

Band = Literal["act", "confirm", "human"]


def entropy(probabilities: Mapping[str, float]) -> float:
    total = 0.0
    for mass in probabilities.values():
        if mass <= 0:
            continue
        total -= mass * math.log(mass)
    return total


def confidence_from_distribution(probabilities: Mapping[str, float]) -> float:
    """Normalized inverse entropy in [0, 1]. Flatter → lower confidence.

    One-hot is 1. Uniform over K≥2 is 0. A single bin is 1 by definition.
    """
    values = [max(0.0, float(p)) for p in probabilities.values()]
    k = len(values)
    if k == 0:
        return 0.0
    if k == 1:
        return 1.0
    total = sum(values)
    if total <= 0:
        return 0.0
    normalized = [p / total for p in values]
    max_h = math.log(k)
    if max_h <= 0:
        return 1.0
    h = entropy(dict(enumerate(normalized)))
    conf = 1.0 - (h / max_h)
    return max(0.0, min(1.0, round(conf, 2)))


def raw_margin(probabilities: Mapping[str, float]) -> float:
    ordered = sorted((float(p) for p in probabilities.values()), reverse=True)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    return round(ordered[0] - ordered[1], 4)


def route_band(
    confidence: float,
    *,
    low: float = 0.5,
    high: float = 0.8,
) -> Band:
    """Three-path routing from TypeSafe's confidence cookbook. Thresholds are caller-owned."""
    if confidence < low:
        return "human"
    if confidence < high:
        return "confirm"
    return "act"
