from __future__ import annotations

from evals.holdout import cases
from evals.jevbeat import run_provider, weakest_axis


def test_holdout_has_labeled_ground_truth() -> None:
    rows = cases()
    assert len(rows) >= 100
    labels = {row["labels"]["department"]["choice"] for row in rows}
    assert labels == {"billing", "technical", "sales"}
    assert all("ticket" in row["state"] for row in rows)


def test_jevbeat_stub_runs_small_limit() -> None:
    row = run_provider(
        provider="stub",
        model="stub",
        fanout="auto",
        scale_temperature=None,
        limit=9,
        nativeness=1,
    )
    assert row["n"] == 9
    assert row["errors"] == 0
    assert "p50" in row["latency_ms"]
    assert row["nativeness"] == 1
    assert "ece_maxprob" in row
    assert weakest_axis(row) in {"latency", "calibration", "accuracy", "cost", "nativeness"}


def test_cursor_nativeness_is_second_harness() -> None:
    fake = {
        "nativeness": 0,
        "latency_ms": {"p50": 1.0},
        "ece": 0.01,
        "mean_accuracy": 0.99,
        "cost_usd_per_mtok_assumed": 0.0,
    }
    assert weakest_axis(fake) == "nativeness"
