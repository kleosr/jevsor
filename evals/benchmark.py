"""Quality snapshot for before/after comparisons. Does not invoke pytest."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _round_tree(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, dict):
        return {k: _round_tree(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_round_tree(v) for v in value]
    return value


def quality_from_answers(payload: dict[str, Any]) -> dict[str, Any]:
    answers = payload["answers"]
    sums: dict[str, float] = {}
    nouls: dict[str, float] = {}
    for key, ans in answers.items():
        if "probabilities" in ans:
            sums[key] = round(sum(ans["probabilities"].values()), 4)
        if ans.get("type") == "noul":
            nouls[key] = round(float(ans["noul"]), 4)
    return {
        "keys": sorted(answers),
        "types": {k: answers[k]["type"] for k in sorted(answers)},
        "provenances": {k: answers[k]["provenance"] for k in sorted(answers)},
        "mixed_provenance": bool(payload.get("mixed_provenance")),
        "probability_sums": sums,
        "nouls": nouls,
    }


def snapshot(*, repeats: int = 5) -> dict[str, Any]:
    from evals.calibration import load_jsonl, report
    from jevsor.mcp_server import evaluate_payload
    from jevsor.runner import Client
    from jevsor.version import __version__

    golden = json.loads((ROOT / "tests" / "fixtures" / "golden_request.json").read_text(encoding="utf-8"))
    times: list[float] = []
    last: dict[str, Any] | None = None
    for _ in range(repeats):
        start = time.perf_counter()
        with Client(provider="stub", model="stub", fanout="isolated") as client:
            last = client.evaluate(golden).model_dump()
        times.append((time.perf_counter() - start) * 1000)
    assert last is not None
    mcp = evaluate_payload(
        golden["state"],
        golden["questions"],
        provider="stub",
        model="stub",
        fanout="isolated",
    )
    labels = load_jsonl(ROOT / "evals" / "sample_labels.jsonl")
    cal = report(labels)
    ece = {
        prov: round(float(block["ece"]), 4)
        for prov, block in cal["by_provenance"].items()
    }
    times.sort()
    mid = times[len(times) // 2]
    return {
        "jevsor_version": __version__,
        "quality": {
            "client": quality_from_answers(last),
            "mcp": quality_from_answers(mcp),
            "ece_by_provenance": ece,
        },
        "perf": {"median_ms": round(mid, 3), "repeats": repeats},
    }


def compare(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    bq, aq = before["quality"], after["quality"]
    if bq != aq:
        failures.append(f"quality mismatch: before={bq} after={aq}")
    if before.get("jevsor_version") != after.get("jevsor_version"):
        failures.append("version mismatch")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="jevsor quality snapshot")
    parser.add_argument("--write", type=Path)
    parser.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"), type=Path)
    parser.add_argument("--check", type=Path, help="compare a fresh snapshot to this pin")
    args = parser.parse_args(argv)
    if args.compare:
        before = json.loads(args.compare[0].read_text(encoding="utf-8"))
        after = json.loads(args.compare[1].read_text(encoding="utf-8"))
        failures = compare(before, after)
        print(json.dumps({"ok": not failures, "failures": failures, "perf": {"before": before.get("perf"), "after": after.get("perf")}}, indent=2))
        return 1 if failures else 0
    snap = _round_tree(snapshot())
    if args.check:
        pin = json.loads(args.check.read_text(encoding="utf-8"))
        failures = compare(pin, snap)
        print(json.dumps({"ok": not failures, "failures": failures, "perf": snap["perf"]}, indent=2))
        return 1 if failures else 0
    text = json.dumps(snap, indent=2)
    if args.write:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
