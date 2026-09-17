"""ECE and temperature-scaling *report*. Never auto-applies T."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any


def expected_calibration_error(
    confidences: Sequence[float],
    correct: Sequence[bool],
    *,
    bins: int = 10,
) -> tuple[float, list[dict[str, Any]]]:
    if len(confidences) != len(correct) or not confidences:
        raise ValueError("confidences and correct must be nonempty and aligned")
    edges = [i / bins for i in range(bins + 1)]
    table: list[dict[str, float]] = []
    ece = 0.0
    n = len(confidences)
    for b in range(bins):
        lo, hi = edges[b], edges[b + 1]
        idx = [
            i
            for i, c in enumerate(confidences)
            if (c >= lo and c < hi) or (b == bins - 1 and c == 1.0)
        ]
        if not idx:
            table.append({"lo": lo, "hi": hi, "n": 0, "acc": None, "conf": None})
            continue
        acc = sum(1 for i in idx if correct[i]) / len(idx)
        conf = sum(confidences[i] for i in idx) / len(idx)
        ece += (len(idx) / n) * abs(acc - conf)
        table.append({"lo": lo, "hi": hi, "n": len(idx), "acc": acc, "conf": conf})
    return ece, table


def nll(probabilities: Sequence[float], labels: Sequence[int]) -> float:
    total = 0.0
    for p, y in zip(probabilities, labels, strict=True):
        p = min(1 - 1e-12, max(1e-12, p))
        total += -math.log(p if y else (1 - p))
    return total / len(labels)


def fit_temperature(probabilities: Sequence[float], labels: Sequence[int]) -> float:
    """Grid-search T on binary P(true). Report only — caller applies."""
    best_t = 1.0
    best = nll(probabilities, labels)
    t = 0.05
    while t <= 5.0:
        scaled = [_scale(p, t) for p in probabilities]
        loss = nll(scaled, labels)
        if loss < best:
            best = loss
            best_t = t
        t = round(t + 0.05, 10)
    return best_t


def _scale(p: float, temperature: float) -> float:
    p = min(1 - 1e-12, max(1e-12, p))
    logit = math.log(p / (1 - p))
    s = 1 / (1 + math.exp(-logit / temperature))
    return s


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_prov: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_prov.setdefault(row.get("provenance", "unknown"), []).append(row)
    out: dict[str, Any] = {"n": len(rows), "by_provenance": {}}
    for prov, group in by_prov.items():
        conf = [float(r["confidence"]) for r in group]
        correct = [bool(r["correct"]) for r in group]
        ece, table = expected_calibration_error(conf, correct)
        block: dict[str, Any] = {"n": len(group), "ece": round(ece, 4), "reliability": table}
        if all("probability" in r and "label" in r for r in group):
            probs = [float(r["probability"]) for r in group]
            labels = [int(r["label"]) for r in group]
            t = fit_temperature(probs, labels)
            block["suggested_temperature"] = t
            block["note"] = "suggested_temperature is a report. jevsor does not apply it."
        out["by_provenance"][prov] = block
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Calibration report. Does not mutate answers.")
    parser.add_argument("labels", type=Path)
    args = parser.parse_args(argv)
    rows = load_jsonl(args.labels)
    print(json.dumps(report(rows), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
