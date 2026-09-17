from __future__ import annotations

import pytest

from jevsor.confidence import route_band
from jevsor.contract import Choice, ChoiceAnswer, Noul, NoulAnswer
from jevsor.policy import (
    Gate,
    answer_band,
    answers_disagree,
    gate_satisfied,
    noul_certainty,
    parse_gate,
    route_answers,
    select_escalation,
    select_speculative,
)


def _choice(choice: str, probs: dict[str, float], confidence: float | None = None) -> ChoiceAnswer:
    from jevsor.confidence import confidence_from_distribution

    return ChoiceAnswer(
        choice=choice,
        probabilities=probs,
        confidence=confidence if confidence is not None else confidence_from_distribution(probs),
        provenance="prompted",
    )


def test_noul_certainty_peaks_at_edges() -> None:
    assert noul_certainty(0.5) == 0.0
    assert noul_certainty(1.0) == 1.0
    assert noul_certainty(0.0) == 1.0
    assert noul_certainty(0.75) == 0.5


def test_answer_band_uses_noul_peakedness() -> None:
    unsure = NoulAnswer(noul=0.51, provenance="prompted")
    sure = NoulAnswer(noul=0.95, provenance="prompted")
    assert answer_band(unsure) == "human"
    assert answer_band(sure) == "act"


def test_gate_requires_matching_choice() -> None:
    answers = {"dept": _choice("billing", {"billing": 0.9, "tech": 0.1})}
    gate = parse_gate({"question": "dept", "equals": "tech"})
    assert gate_satisfied(gate, answers) is False
    assert gate_satisfied(parse_gate({"question": "dept", "equals": "billing"}), answers) is True


def test_unconditional_gate() -> None:
    assert gate_satisfied(Gate(), {}) is True


def test_select_speculative_skips_unmet_gate() -> None:
    speculative = {"sev": object(), "always": object()}
    answers = {"dept": _choice("billing", {"billing": 1.0, "tech": 0.0})}
    gates = {
        "sev": parse_gate({"question": "dept", "equals": "tech"}),
        "always": Gate(),
    }
    run, skipped = select_speculative(speculative, gates, answers)
    assert run == ["always"]
    assert skipped == ["sev"]


def test_select_escalation_bands() -> None:
    answers = {
        "a": _choice("x", {"x": 1.0, "y": 0.0}, confidence=0.95),
        "b": _choice("x", {"x": 0.55, "y": 0.45}, confidence=0.01),
        "c": _choice("x", {"x": 0.7, "y": 0.3}, confidence=0.6),
    }
    assert select_escalation(answers, False) == []
    assert select_escalation(answers, "human") == ["b"]
    assert set(select_escalation(answers, "confirm")) == {"b", "c"}


def test_answers_disagree_argmax() -> None:
    left = _choice("billing", {"billing": 0.7, "tech": 0.3})
    right = _choice("tech", {"billing": 0.2, "tech": 0.8})
    same = _choice("billing", {"billing": 0.9, "tech": 0.1})
    assert answers_disagree(left, right) is True
    assert answers_disagree(left, same) is False
    assert answers_disagree(
        NoulAnswer(noul=0.1, provenance="prompted"),
        NoulAnswer(noul=0.8, provenance="prompted"),
    )


def test_choice_route_runner_up_follows_selected_winner() -> None:
    # Prompted JSON can keep an explicit choice that is not the probability mode.
    routed = route_answers(
        {"dept": _choice("tech", {"billing": 0.6, "tech": 0.3, "sales": 0.1}, confidence=0.2)}
    )
    row = routed["dept"]
    assert row["choice"] == "tech"
    assert row["winner"] == "tech"
    assert row["runner_up"] == "billing"
    assert row["margin"] == pytest.approx(-0.3)


def test_route_answers_mcp_shape() -> None:
    answers = {
        "dept": _choice("billing", {"billing": 0.9, "tech": 0.1}, confidence=0.9),
        "urg": NoulAnswer(noul=0.8, provenance="measured"),
    }
    routed = route_answers(answers)
    assert routed["dept"]["band"] == "act"
    assert routed["dept"]["choice"] == "billing"
    assert routed["dept"]["winner"] == "billing"
    assert routed["dept"]["runner_up"] == "tech"
    assert routed["urg"]["noul"] == 0.8
    assert routed["urg"]["winner"] == "yes"
    assert routed["urg"]["band"] == route_band(noul_certainty(0.8))


def test_route_report_worst_band_and_disagreement() -> None:
    from jevsor.policy import fail_closed, route_report

    answers = {
        "dept": _choice("billing", {"billing": 0.9, "tech": 0.1}, confidence=0.9),
        "risk": _choice("high", {"high": 0.55, "low": 0.45}, confidence=0.01),
    }
    report = route_report(answers)
    assert report["decision"] == "human"
    assert report["worst_band"] == "human"
    assert report["degrade"] is None
    assert report["routes"]["dept"]["winner"] == "billing"

    forced = route_report(
        {"dept": _choice("billing", {"billing": 0.95, "tech": 0.05}, confidence=0.9)},
        disagreed=["dept"],
    )
    assert forced["decision"] == "human"
    assert forced["routes"]["dept"]["disagreed"] is True
    assert forced["routes"]["dept"]["band"] == "human"

    closed = fail_closed(Exception("mcp down"), status=502)
    assert closed["decision"] == "human"
    assert closed["degrade"] == "human"
    assert closed["reason"] == "provider"
    assert closed["routes"] == {}


def test_parse_gate_rejects_bad_band() -> None:
    with pytest.raises(ValueError):
        parse_gate({"question": "x", "band": "maybe"})


def test_helpers_exist_for_typed_questions() -> None:
    assert Choice("Which?", {"a": None, "b": None}).type == "choice"
    assert Noul("Y?").type == "noul"
