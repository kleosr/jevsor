"""Jev-beat harness. Honest metrics. Does not call TypeSafe."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evals.calibration import expected_calibration_error
from evals.holdout import cases
from jevsor import Client
from jevsor.calibrate import fit_distribution_temperature, scale_distribution
from jevsor.policy import route_report
from jevsor.version import __version__

# Published Jev figures are self-reported and unreproduced. Targets, not facts.
TARGETS = {
    "latency_p50_ms": 70.0,
    "cost_usd_per_mtok": 0.042,
    "ece": 0.05,
    "accuracy": 0.678,
    "nativeness": 1,
}


def _score_case(answers: dict[str, Any], labels: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    dept = answers["department"]
    probs = dict(dept.get("probabilities") or {})
    out["choice_ok"] = dept["choice"] == labels["department"]["choice"]
    out["choice_conf"] = float(dept.get("confidence") or 0)
    out["choice_pmax"] = max(probs.values()) if probs else 0.0
    out["choice_probs"] = probs
    out["choice_label"] = labels["department"]["choice"]
    noul = float(answers["is_urgent"]["noul"])
    want_urgent = bool(labels["is_urgent"]["noul_true"])
    out["noul_ok"] = (noul >= 0.5) == want_urgent
    out["brier"] = (noul - (1.0 if want_urgent else 0.0)) ** 2
    heat = float(answers["frustration"]["score"])
    out["score_mae"] = abs(heat - float(labels["frustration"]["score"]))
    return out


def run_provider(
    *,
    provider: str,
    model: str,
    fanout: str,
    scale_temperature: float | None,
    limit: int | None,
    nativeness: int,
) -> dict[str, Any]:
    subset = cases()[:limit] if limit else cases()
    latencies: list[float] = []
    tokens_in = 0
    tokens_out = 0
    choice_hits = 0
    noul_hits = 0
    mae: list[float] = []
    brier: list[float] = []
    confs: list[float] = []
    pmaxs: list[float] = []
    correct: list[bool] = []
    choice_pairs: list[tuple[dict[str, float], str]] = []
    errors = 0
    last_error = None
    with Client(
        provider=provider,
        model=model,
        fanout=fanout,  # type: ignore[arg-type]
        scale_temperature=scale_temperature,
    ) as client:
        for case in subset:
            start = time.perf_counter()
            try:
                response = client.evaluate(state=case["state"], questions=case["questions"])
                elapsed = (time.perf_counter() - start) * 1000
                latencies.append(elapsed)
                payload = response.model_dump()
                tokens_in += payload["usage"]["input_tokens"]
                tokens_out += payload["usage"]["output_tokens"]
                scored = _score_case(payload["answers"], case["labels"])
                choice_hits += int(scored["choice_ok"])
                noul_hits += int(scored["noul_ok"])
                mae.append(scored["score_mae"])
                brier.append(scored["brier"])
                confs.append(scored["choice_conf"])
                pmaxs.append(float(scored["choice_pmax"]))
                correct.append(bool(scored["choice_ok"]))
                if scored["choice_probs"]:
                    choice_pairs.append((scored["choice_probs"], scored["choice_label"]))
                route_report(payload["answers"])
            except Exception as exc:  # noqa: BLE001 — bench must survive a bad case
                errors += 1
                latencies.append((time.perf_counter() - start) * 1000)
                confs.append(0.0)
                pmaxs.append(0.0)
                correct.append(False)
                last_error = str(exc)
    n = max(1, len(subset))
    latencies.sort()

    def pct(p: float) -> float:
        if not latencies:
            return 0.0
        idx = min(len(latencies) - 1, max(0, math.ceil(p / 100 * len(latencies)) - 1))
        return round(latencies[idx], 3)

    ece_inv, table_inv = expected_calibration_error(confs, correct) if confs else (1.0, [])
    ece_max, table_max = expected_calibration_error(pmaxs, correct) if pmaxs else (1.0, [])
    choice_acc = choice_hits / n
    mean_acc = (choice_acc + noul_hits / n) / 2
    stub_cost = 0.0 if provider == "stub" else None
    return {
        "jevsor_version": __version__,
        "provider": provider,
        "model": model,
        "fanout": fanout,
        "scale_temperature": scale_temperature,
        "n": len(subset),
        "errors": errors,
        "last_error": last_error,
        "latency_ms": {
            "p50": pct(50),
            "p95": pct(95),
            "p99": pct(99),
            "mean": round(statistics.fmean(latencies), 3) if latencies else 0,
            "stdev": round(statistics.pstdev(latencies), 3) if len(latencies) > 1 else 0,
        },
        "tokens": {"input": tokens_in, "output": tokens_out},
        "cost_usd_per_mtok_assumed": stub_cost,
        "cost_note": "stub is free local hash, not Jev's $0.042/MTok. Cursor Cloud Agents are billed as agent usage.",
        "choice_accuracy": round(choice_acc, 4),
        "noul_accuracy": round(noul_hits / n, 4),
        "score_mae": round(statistics.fmean(mae), 4) if mae else None,
        "noul_brier": round(statistics.fmean(brier), 4) if brier else None,
        "mean_accuracy": round(mean_acc, 4),
        "structural_validity": round((n - errors) / n, 4),
        "ece": round(float(ece_max), 4),
        "ece_maxprob": round(float(ece_max), 4),
        "ece_inverse_entropy": round(float(ece_inv), 4),
        "reliability": table_max,
        "reliability_inverse_entropy": table_inv,
        "nativeness": nativeness,
        "calls_per_case": "isolated N heads" if fanout != "batch" else "one prompted JSON unless logprobs isolate",
        "http_calls_note": "stub: in-process. cursor: one Cloud Agent run per complete() (hidden N if isolated).",
        "targets": TARGETS,
        "gaps": {
            "latency_p50_ms": round(pct(50) - TARGETS["latency_p50_ms"], 3),
            "ece": round(float(ece_max) - TARGETS["ece"], 4),
            "accuracy": round(mean_acc - TARGETS["accuracy"], 4),
        },
        "_choice_pairs": choice_pairs,
    }


def weakest_axis(row: dict[str, Any]) -> str:
    """Largest relative miss vs target. Nativeness is binary."""
    if row["nativeness"] != 1:
        return "nativeness"
    rel = {
        "latency": max(0.0, row["latency_ms"]["p50"] / TARGETS["latency_p50_ms"] - 1),
        "calibration": max(0.0, row["ece"] / TARGETS["ece"] - 1),
        "accuracy": max(0.0, TARGETS["accuracy"] / max(row["mean_accuracy"], 1e-6) - 1),
        "cost": 0.0 if row["cost_usd_per_mtok_assumed"] in (None, 0.0) else max(
            0.0, float(row["cost_usd_per_mtok_assumed"]) / TARGETS["cost_usd_per_mtok"] - 1
        ),
    }
    return max(rel, key=lambda k: rel[k])


def posthoc_temperature(row: dict[str, Any], *, fit_split: int) -> dict[str, Any]:
    pairs: list[tuple[dict[str, float], str]] = list(row.get("_choice_pairs") or [])
    if fit_split <= 0 or len(pairs) <= fit_split:
        return {"skipped": True, "reason": "not enough labeled choice rows"}
    train, test = pairs[:fit_split], pairs[fit_split:]
    fitted = fit_distribution_temperature(train)
    confs: list[float] = []
    correct: list[bool] = []
    flips = 0
    for probs, label in test:
        scaled = scale_distribution(probs, fitted)
        original = max(probs, key=lambda k: probs[k])
        rounded = max(scaled, key=lambda k: scaled[k])
        if rounded != original:
            flips += 1
        confs.append(float(scaled.get(original, 0.0)))
        correct.append(original == label)
    ece, table = expected_calibration_error(confs, correct)
    acc = sum(correct) / len(correct)
    return {
        "skipped": False,
        "fit_n": len(train),
        "eval_n": len(test),
        "fitted_temperature": fitted,
        "ece_maxprob": round(float(ece), 4),
        "choice_accuracy": round(acc, 4),
        "rounded_argmax_flips": flips,
        "note": "T-scaling is post-hoc. Accuracy uses the original argmax; rounding must not retie the winner.",
        "reliability": table,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Honest System One bench. Never calls Jev.")
    parser.add_argument("--provider", default="stub")
    parser.add_argument("--model", default="stub")
    parser.add_argument("--fanout", default="auto")
    parser.add_argument("--scale-temperature", type=float, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--nativeness", type=int, default=None)
    parser.add_argument("--fit-split", type=int, default=26)
    parser.add_argument("--write", type=Path)
    args = parser.parse_args(argv)
    nativeness = args.nativeness
    if nativeness is None:
        nativeness = 0 if args.provider == "cursor" else 1
    row = run_provider(
        provider=args.provider,
        model=args.model,
        fanout=args.fanout,
        scale_temperature=args.scale_temperature,
        limit=args.limit,
        nativeness=nativeness,
    )
    row["posthoc_temperature"] = posthoc_temperature(row, fit_split=args.fit_split)
    row.pop("_choice_pairs", None)
    row["weakest_axis"] = weakest_axis(row)
    text = json.dumps(row, indent=2)
    if args.write:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if row["errors"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
