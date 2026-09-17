from __future__ import annotations

from jevsor.contract import Choice, Noul, Score
from jevsor.schedule import can_measure_all, resolve_fanout


def test_resolve_fanout_measured_is_isolated() -> None:
    assert resolve_fanout("auto", measured=True) == "isolated"
    assert resolve_fanout("batch", measured=True) == "isolated"
    assert resolve_fanout("isolated", measured=False) == "isolated"


def test_resolve_fanout_prompted_batch_is_one_json() -> None:
    assert resolve_fanout("auto", measured=False) == "batch"
    assert resolve_fanout("batch", measured=False) == "batch"


def test_can_measure_all_rejects_wide_choice() -> None:
    small = {"d": Choice("Which?", {"a": None, "b": None}), "u": Noul("Y?")}
    wide = {"w": Choice("Pick", {f"opt{i}": None for i in range(21)})}
    score = {"s": Score("lvl", ["a", "b"])}
    assert can_measure_all(small) is True
    assert can_measure_all(wide) is False
    assert can_measure_all(score) is True
