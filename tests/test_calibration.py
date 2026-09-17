from __future__ import annotations

from evals.calibration import expected_calibration_error, fit_temperature, report


def test_ece_known_fixture() -> None:
    conf = [0.0, 0.0, 1.0, 1.0]
    correct = [False, False, True, True]
    ece, table = expected_calibration_error(conf, correct, bins=2)
    assert ece == 0.0
    nonempty = [row for row in table if row["n"]]
    assert nonempty


def test_ece_miscalibrated() -> None:
    conf = [0.9, 0.9, 0.9, 0.9]
    correct = [False, False, False, True]
    ece, _ = expected_calibration_error(conf, correct, bins=2)
    assert ece > 0.5


def test_temperature_report_only() -> None:
    t = fit_temperature([0.9, 0.9, 0.1, 0.1], [0, 0, 1, 1])
    assert t != 1.0


def test_sample_labels_bins_by_provenance() -> None:
    from pathlib import Path
    import json

    path = Path(__file__).resolve().parents[1] / "evals" / "sample_labels.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    out = report(rows)
    assert "measured" in out["by_provenance"]
    assert "prompted" in out["by_provenance"]
    assert "suggested_temperature" in out["by_provenance"]["measured"]
