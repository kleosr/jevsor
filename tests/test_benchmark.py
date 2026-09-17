from __future__ import annotations

import json
from pathlib import Path

from evals.benchmark import compare, snapshot

PIN = Path(__file__).resolve().parents[1] / "evals" / "quality_pin.json"


def test_quality_pin_holds() -> None:
    pin = json.loads(PIN.read_text(encoding="utf-8"))
    failures = compare(pin, snapshot())
    assert failures == []


def test_client_and_mcp_quality_match() -> None:
    snap = snapshot(repeats=1)
    assert snap["quality"]["client"] == snap["quality"]["mcp"]
    assert snap["quality"]["client"]["keys"] == ["department", "frustration", "is_urgent"]
    assert snap["quality"]["ece_by_provenance"]["measured"] >= 0


def test_plugin_launches_with_uvx() -> None:
    plugin = json.loads((Path(__file__).resolve().parents[1] / "plugin" / "mcp.json").read_text(encoding="utf-8"))
    server = plugin["mcpServers"]["jevsor"]
    assert server["command"] == "uvx"
    assert "--from" in server["args"]
    assert "jevsor-mcp" in server["args"]
