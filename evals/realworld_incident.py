"""Live engineering scenario: incident + PR, Client + MCP, code-owned routing."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jevsor import Client, Choice, Noul, Score, route_band
from jevsor.mcp_server import evaluate_payload

INCIDENT_STATE = {
    "channel": "#inc-checkout",
    "opened_at": "2026-09-17T21:08:00Z",
    "symptom": "checkout POST /v1/pay returns 502 for ~18% of requests",
    "started_after": "payments-api deploy 14:02 UTC (sha 7f3c1a)",
    "error": "upstream connect error to billing-ledger:8443",
    "slo": "checkout availability 99.9%; currently 82% over 15m",
    "recent_changes": [
        "payments-api: timeout 2s -> 800ms on ledger client",
        "no billing-ledger deploy in 11 days",
    ],
}

PR_STATE = {
    "repo": "payments-api",
    "pr": 1842,
    "title": "Tighten ledger client timeout to 800ms",
    "author": "oncall-bot",
    "diffstat": "+24 / -6",
    "tests": "unit suite green; no load or timeout integration test",
    "review": "one approval from intern; staff engineer requested soak but not blocking",
    "risk_notes": "timeout change is in the blast radius of the open checkout incident",
}


def _questions_incident() -> dict[str, Any]:
    return {
        "service": Choice(
            "Which service is the most likely source of the 502s?",
            {
                "payments_api": "Our checkout/payments-api process, recent deploy",
                "billing_ledger": "Upstream ledger, no recent deploy",
                "edge": "CDN/gateway, not named in the error",
            },
        ),
        "rollback": Noul(
            "Should we roll back payments-api sha 7f3c1a now?",
            {
                "true": "Rollback is the fastest way to restore the SLO",
                "false": "Keep the deploy; debug or mitigate in place",
            },
        ),
        "severity": Score(
            "Incident severity for customer checkout",
            ["Sev4 noise", "Sev3 degraded", "Sev2 major", "Sev1 outage"],
        ),
        "deploy_regression": Noul("Is this a regression from the 14:02 deploy?"),
    }


def _questions_pr() -> dict[str, Any]:
    return {
        "merge": Choice(
            "What should happen to PR 1842 right now?",
            {
                "merge": "Merge as-is",
                "hold": "Hold until the checkout incident is closed",
                "revert_prep": "Prepare revert of the already-shipped timeout change",
            },
        ),
        "test_gap": Noul("Does this PR lack tests that would have caught the timeout failure?"),
        "risk": Score("Merge risk while the incident is open", ["Low", "Medium", "High"]),
    }


def _route_incident(answers: dict[str, Any]) -> str:
    rollback = answers["rollback"]
    severity = answers["severity"]
    service = answers["service"]
    if severity.score >= 2.0 and rollback.noul >= 0.6:
        return "rollback_payments_api"
    if service.confidence < 0.5:
        return "page_human"
    if route_band(service.confidence) == "act" and rollback.noul < 0.4:
        return "mitigate_in_place"
    return "confirm_with_oncall"


def _route_pr(answers: dict[str, Any], incident_action: str) -> str:
    merge = answers["merge"]
    risk = answers["risk"]
    if incident_action == "rollback_payments_api":
        return "hold_and_prep_revert"
    if risk.score >= 1.5 or merge.confidence < 0.6:
        return "hold"
    if merge.choice == "merge" and route_band(merge.confidence) == "act":
        return "merge"
    return str(merge.choice)


def _payload(questions: dict[str, Any]) -> dict[str, Any]:
    return {key: q.model_dump() for key, q in questions.items()}


def _dump_row(ans: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "type": ans.type if not isinstance(ans, dict) else ans["type"],
        "provenance": ans.provenance if not isinstance(ans, dict) else ans["provenance"],
        "truncated": (ans.truncated if not isinstance(ans, dict) else ans.get("truncated", False)),
    }
    if row["type"] == "choice":
        row["choice"] = ans.choice if not isinstance(ans, dict) else ans["choice"]
        row["confidence"] = ans.confidence if not isinstance(ans, dict) else ans["confidence"]
        row["probabilities"] = ans.probabilities if not isinstance(ans, dict) else ans["probabilities"]
    elif row["type"] == "score":
        row["score"] = ans.score if not isinstance(ans, dict) else ans["score"]
        row["confidence"] = ans.confidence if not isinstance(ans, dict) else ans["confidence"]
        row["probabilities"] = ans.probabilities if not isinstance(ans, dict) else ans["probabilities"]
    else:
        row["noul"] = ans.noul if not isinstance(ans, dict) else ans["noul"]
    return row


def _dump_answers(answers: dict[str, Any]) -> dict[str, Any]:
    return {key: _dump_row(ans) for key, ans in answers.items()}


def _ollama() -> str:
    try:
        import httpx

        httpx.get("http://127.0.0.1:11434/api/tags", timeout=1.5)
        return "reachable"
    except Exception as exc:
        return f"unreachable ({type(exc).__name__})"


def run() -> dict[str, Any]:
    incident_q = _questions_incident()
    pr_q = _questions_pr()
    t0 = time.perf_counter()
    with Client(provider="stub", model="stub", fanout="isolated") as client:
        incident = client.evaluate(state=INCIDENT_STATE, questions=incident_q)
        pr = client.evaluate(state=PR_STATE, questions=pr_q)
    client_ms = (time.perf_counter() - t0) * 1000
    incident_action = _route_incident(incident.answers)
    pr_action = _route_pr(pr.answers, incident_action)

    t1 = time.perf_counter()
    mcp_incident = evaluate_payload(
        INCIDENT_STATE,
        _payload(incident_q),
        provider="stub",
        model="stub",
        fanout="isolated",
    )
    mcp_ms = (time.perf_counter() - t1) * 1000
    incident_dump = _dump_answers(incident.answers)
    mcp_dump = _dump_answers(mcp_incident["answers"])
    return {
        "provider": "stub",
        "model": incident.model,
        "jevsor_version": incident.debug.jevsor_version if incident.debug else None,
        "fanout": "isolated",
        "ollama": _ollama(),
        "client_ms": round(client_ms, 2),
        "mcp_ms": round(mcp_ms, 2),
        "incident_action": incident_action,
        "pr_action": pr_action,
        "incident": incident_dump,
        "pr": _dump_answers(pr.answers),
        "mcp_incident": mcp_dump,
        "client_mcp_match": incident_dump == mcp_dump,
        "usage": {
            "incident": incident.usage.model_dump(),
            "pr": pr.usage.model_dump(),
        },
        "debug": incident.debug.model_dump() if incident.debug else None,
    }


def main() -> int:
    print(json.dumps(run(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
