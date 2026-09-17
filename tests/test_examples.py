from __future__ import annotations

import runpy
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_triage_example() -> None:
    ns = runpy.run_path(str(EXAMPLES / "triage.py"), run_name="not_main")
    assert ns["main"]() == 0


def test_composite_example() -> None:
    ns = runpy.run_path(str(EXAMPLES / "composite_routing.py"), run_name="not_main")
    assert ns["main"]() == 0


def test_local_ollama_example_exits() -> None:
    ns = runpy.run_path(str(EXAMPLES / "local_ollama.py"), run_name="not_main")
    assert ns["main"]() == 0
