from __future__ import annotations

import runpy
from pathlib import Path

EVAL = Path(__file__).resolve().parents[1] / "evals" / "realworld_incident.py"


def test_realworld_incident_client_matches_mcp() -> None:
    ns = runpy.run_path(str(EVAL), run_name="not_main")
    report = ns["run"]()
    assert report["client_mcp_match"] is True
    assert report["incident_action"] == "page_human"
    assert report["pr_action"] == "hold"
    assert report["incident"]["service"]["confidence"] < 0.5
    assert report["incident"]["service"]["provenance"] == "measured"
    assert report["incident"]["rollback"]["provenance"] == "measured"
    assert report["pr"]["merge"]["type"] == "choice"
