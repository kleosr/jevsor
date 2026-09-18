from __future__ import annotations

from jevsor.calibrate import (
    fit_distribution_temperature,
    rescale_answer,
    scale_distribution,
)
from jevsor.capabilities import cache_key, clear_probe_cache, remember, remembered
from jevsor.contract import ChoiceAnswer, NoulAnswer, ScoreAnswer
from jevsor import Client, Noul


def test_scale_distribution_sharpens_and_flattens() -> None:
    peaked = {"a": 0.7, "b": 0.2, "c": 0.1}
    sharp = scale_distribution(peaked, 0.3)
    flat = scale_distribution(peaked, 4.0)
    assert sharp["a"] >= peaked["a"]
    assert flat["a"] <= peaked["a"]
    assert abs(sum(sharp.values()) - 1) < 0.05
    assert abs(sum(flat.values()) - 1) < 0.05


def test_rescale_skips_prompted() -> None:
    ans = NoulAnswer(noul=0.8, provenance="prompted")
    assert rescale_answer(ans, 0.2).noul == 0.8


def test_rescale_measured_noul() -> None:
    ans = NoulAnswer(noul=0.8, provenance="measured")
    out = rescale_answer(ans, 0.4)
    assert out.noul >= 0.8


def test_probe_cache_includes_endpoint() -> None:
    clear_probe_cache()
    remember("openai_compat", "m", True, "http://a")
    assert remembered("openai_compat", "m", "http://a") is True
    assert remembered("openai_compat", "m", "http://b") is None
    assert cache_key("openai_compat", "m", "http://a") != cache_key("openai_compat", "m", "http://b")
    assert cache_key("openai_compat", "m-v1") != cache_key("openai_compat", "m-v2")
    clear_probe_cache()


def test_choice_rescale_keeps_schema() -> None:
    ans = ChoiceAnswer(
        choice="a",
        probabilities={"a": 0.7, "b": 0.3},
        confidence=0.12,
        provenance="measured",
    )
    out = rescale_answer(ans, 0.5)
    assert set(out.probabilities) == {"a", "b"}
    assert abs(sum(out.probabilities.values()) - 1) < 0.05
    assert max(out.probabilities, key=lambda k: out.probabilities[k]) == "a"


def test_scale_does_not_change_argmax() -> None:
    peaked = {"a": 0.7, "b": 0.2, "c": 0.1}
    for temperature in (0.3, 1.0, 4.0):
        scaled = scale_distribution(peaked, temperature)
        assert max(scaled, key=lambda k: scaled[k]) == "a"


def test_rescale_preserves_choice_on_near_tie() -> None:
    ans = ChoiceAnswer(
        choice="a",
        probabilities={"a": 0.34, "b": 0.33, "c": 0.33},
        confidence=0.01,
        provenance="measured",
    )
    out = rescale_answer(ans, 5.0)
    assert out.choice == "a"


def test_score_rescale_keeps_levels() -> None:
    ans = ScoreAnswer(
        score=0.4,
        probabilities={"Calm": 0.7, "Frustrated": 0.2, "Very angry": 0.1},
        confidence=0.2,
        provenance="measured",
    )
    out = rescale_answer(ans, 0.4)
    assert set(out.probabilities) == set(ans.probabilities)
    assert abs(sum(out.probabilities.values()) - 1) < 0.05


def test_fit_temperature_flattens_when_argmax_wrong() -> None:
    rows = [({"a": 0.8, "b": 0.2}, "b")] * 20
    assert fit_distribution_temperature(rows) > 1.0


def test_fit_temperature_sharpens_when_argmax_right() -> None:
    rows = [({"a": 0.65, "b": 0.35}, "a")] * 20
    assert fit_distribution_temperature(rows) <= 1.0


def test_client_scale_temperature_sharpens_measured() -> None:
    with Client("stub", fanout="isolated") as raw:
        before = raw.evaluate(state="x", questions={"u": Noul("Y?")}).answers["u"]
    with Client("stub", fanout="isolated", scale_temperature=0.2) as scaled:
        after = scaled.evaluate(state="x", questions={"u": Noul("Y?")}).answers["u"]
    assert before.provenance == "measured"
    if abs(before.noul - 0.5) > 0.05:
        assert after.noul != before.noul
