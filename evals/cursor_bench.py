"""Live Cursor SDK bench: labeled accuracy + latency. Needs CURSOR_API_KEY."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jevsor import Client, Choice, Noul, Score
from jevsor.errors import JevsorError

# Cursor product models this account can actually run via the SDK.
# composer-2.5:fast is the product default speed variant.
MODELS = [
    "composer-2.5:fast",
    "grok-4.6",
    "gpt-5.6-sol",
    "gpt-5.6-luna:fast",
]


def cases() -> list[dict[str, Any]]:
    all_cases = [
        {
            "id": "payouts",
            "state": {
                "ticket": "Help! My payouts have been failing for 3 days.",
                "account_age_days": 800,
            },
            "questions": {
                "department": Choice(
                    "Which team should handle this?",
                    {
                        "billing": "Payments, invoicing, refunds",
                        "technical": "Bugs, outages, integrations",
                        "sales": "Pricing, upgrades, new accounts",
                    },
                ),
                "frustration": Score(
                    "How frustrated is the customer?",
                    ["Calm", "Frustrated", "Very angry"],
                ),
                "is_urgent": Noul("Does this convey urgency?"),
            },
            "labels": {
                "department": {"choice": "billing"},
                "frustration": {"score_min": 1},
                "is_urgent": {"noul_true": True},
            },
        },
        {
            "id": "checkout_502",
            "state": {
                "channel": "#inc-checkout",
                "symptom": "checkout POST /v1/pay returns 502 for ~18% of requests",
                "started_after": "payments-api deploy 14:02 UTC (sha 7f3c1a)",
                "error": "upstream connect error to billing-ledger:8443",
                "slo": "checkout availability 99.9%; currently 82% over 15m",
                "recent_changes": [
                    "payments-api: timeout 2s -> 800ms on ledger client",
                    "no billing-ledger deploy in 11 days",
                ],
            },
            "questions": {
                "service": Choice(
                    "Which service is the most likely source of the 502s?",
                    {
                        "payments_api": "Our checkout/payments-api process, recent deploy",
                        "billing_ledger": "Upstream ledger, no recent deploy",
                        "edge": "CDN/gateway, not named in the error",
                    },
                ),
                "rollback": Noul("Should we roll back payments-api sha 7f3c1a now?"),
                "severity": Score(
                    "Incident severity for customer checkout",
                    ["Sev4 noise", "Sev3 degraded", "Sev2 major", "Sev1 outage"],
                ),
            },
            "labels": {
                "service": {"choice": "payments_api"},
                "rollback": {"noul_true": True},
                "severity": {"score_min": 2},
            },
        },
        {
            "id": "invoice_where",
            "state": {
                "ticket": "Hi, where do I download invoices from last month?",
            },
            "questions": {
                "department": Choice(
                    "Which team should handle this?",
                    {
                        "billing": "Payments, invoicing, refunds",
                        "technical": "Bugs, outages, integrations",
                        "sales": "Pricing, upgrades, new accounts",
                    },
                ),
                "is_urgent": Noul("Does this convey urgency?"),
                "frustration": Score(
                    "How frustrated is the customer?",
                    ["Calm", "Frustrated", "Very angry"],
                ),
            },
            "labels": {
                "department": {"choice": "billing"},
                "is_urgent": {"noul_true": False},
                "frustration": {"score_max": 0.5},
            },
        },
    ]
    return all_cases


def score_answer(ans: Any, label: dict[str, Any]) -> bool:
    if "choice" in label:
        return getattr(ans, "choice", None) == label["choice"]
    if "noul_true" in label:
        return (float(ans.noul) >= 0.5) is bool(label["noul_true"])
    if "score_min" in label:
        return float(ans.score) >= float(label["score_min"])
    if "score_max" in label:
        return float(ans.score) <= float(label["score_max"])
    raise ValueError(f"unknown label {label}")


def pick_winner(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in rows if r.get("ok")]
    if not ok:
        return {"recommended": None, "best_quality": None, "fastest": None}
    nq = max(int(r.get("n_questions") or 1) for r in ok)
    best = max(ok, key=lambda r: (r["accuracy"], -r["median_ms"]))
    fastest = min(ok, key=lambda r: r["median_ms"])
    bar = best["accuracy"] - (1 / nq)
    contenders = [r for r in ok if r["accuracy"] >= bar]
    recommended = min(contenders, key=lambda r: r["median_ms"])
    return {
        "recommended": recommended["model"],
        "best_quality": best["model"],
        "fastest": fastest["model"],
        "rule": "highest accuracy; if within one question, pick lowest median_ms",
    }


def _run_model(model: str, selected: list[dict[str, Any]]) -> dict[str, Any]:
    times: list[float] = []
    hits = 0
    total = 0
    details: list[dict[str, Any]] = []
    key = os.environ.get("CURSOR_API_KEY", "")
    t_all = time.perf_counter()
    with Client(
        provider="cursor",
        model=model,
        fanout="batch",
        seed=None,
        api_key=key,
        timeout=180.0,
    ) as client:
        for case in selected:
            start = time.perf_counter()
            try:
                result = client.evaluate(state=case["state"], questions=case["questions"])
                err = None
            except JevsorError as exc:
                result = None
                err = f"{type(exc).__name__}: {exc}"
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)
            row: dict[str, Any] = {"id": case["id"], "ms": round(elapsed, 1), "error": err}
            if result is None:
                details.append(row)
                total += len(case["labels"])
                continue
            answers: dict[str, Any] = {}
            for qid, label in case["labels"].items():
                total += 1
                ans = result.answers[qid]
                ok = score_answer(ans, label)
                hits += int(ok)
                payload: dict[str, Any] = {"ok": ok, "type": ans.type}
                if ans.type == "choice":
                    payload["choice"] = ans.choice
                    payload["confidence"] = ans.confidence
                elif ans.type == "score":
                    payload["score"] = ans.score
                    payload["confidence"] = ans.confidence
                else:
                    payload["noul"] = ans.noul
                answers[qid] = payload
            row["answers"] = answers
            row["provenance"] = next(iter(result.answers.values())).provenance
            details.append(row)
    times.sort()
    mid = times[len(times) // 2] if times else 0.0
    return {
        "model": model,
        "ok": hits > 0 and all(d.get("error") is None for d in details),
        "accuracy": round(hits / total, 4) if total else 0.0,
        "hits": hits,
        "n_questions": total,
        "median_ms": round(mid, 1),
        "total_ms": round((time.perf_counter() - t_all) * 1000, 1),
        "cases": details,
    }


def run(models: list[str] | None = None, limit: int = 0) -> dict[str, Any]:
    if not os.environ.get("CURSOR_API_KEY"):
        raise SystemExit("CURSOR_API_KEY is missing")
    selected = cases()[:limit] if limit else cases()
    rows = [_run_model(name, selected) for name in (models or MODELS)]
    return {
        "provider": "cursor",
        "gateway": "Cursor Cloud Agents API https://api.cursor.com (not Token Harbor)",
        "models": rows,
        "pick": pick_winner(rows),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cursor SDK live bench")
    parser.add_argument("--model", action="append")
    parser.add_argument("--write", type=Path)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args(argv)
    report = run(args.model, args.limit)
    text = json.dumps(report, indent=2)
    if args.write:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if report["pick"]["recommended"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
