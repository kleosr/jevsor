from __future__ import annotations

import pytest

from jevsor.confidence import confidence_from_distribution, raw_margin, route_band
from jevsor.errors import ValidationError
from jevsor.letter import SENTINEL_LOGPROB, TokenAlt, canonicalize_token, dist_from_top
from jevsor.validate import distribution_tolerance, round2, validate_distribution, validate_noul, weighted_score


def test_round2() -> None:
    assert round2(0.851) == 0.85
    assert round2(0.859) == 0.86
    assert round2(0.1 + 0.2) == 0.3


def test_distribution_rounding_tolerance() -> None:
    # 0.33 * 3 = 0.99, within 0.005 * 3.
    probs = {"a": 0.33, "b": 0.33, "c": 0.33}
    got = validate_distribution(probs, expected_keys=["a", "b", "c"])
    assert abs(sum(got.values()) - 0.99) < 1e-9
    assert distribution_tolerance(3) >= 0.015


def test_distribution_rejects_bad_sum() -> None:
    with pytest.raises(ValidationError):
        validate_distribution({"a": 0.9, "b": 0.9})


def test_distribution_key_mismatch() -> None:
    with pytest.raises(ValidationError):
        validate_distribution({"a": 0.5, "c": 0.5}, expected_keys=["a", "b"])


def test_noul_bounds() -> None:
    assert validate_noul(0.921) == 0.92
    with pytest.raises(ValidationError):
        validate_noul(1.5)


def test_weighted_score_agrees() -> None:
    levels = ["Calm", "Frustrated", "Very angry"]
    probs = {"Calm": 0.1, "Frustrated": 0.4, "Very angry": 0.5}
    assert weighted_score(probs, levels) == 1.4


def test_confidence_one_hot_is_one() -> None:
    assert confidence_from_distribution({"a": 1.0, "b": 0.0, "c": 0.0}) == 1.0


def test_confidence_uniform_is_zero() -> None:
    assert confidence_from_distribution({"a": 0.5, "b": 0.5}) == 0.0


def test_route_bands() -> None:
    assert route_band(0.2) == "human"
    assert route_band(0.6) == "confirm"
    assert route_band(0.9) == "act"


def test_raw_margin() -> None:
    assert raw_margin({"a": 0.8, "b": 0.2}) == 0.6


def test_letter_space_variants() -> None:
    assert canonicalize_token(" A") == "A"
    assert canonicalize_token("ĠA") == "A"
    letter_to_option = {"A": "billing", "B": "tech"}
    alts = [
        TokenAlt(token=" A", logprob=-0.1),
        TokenAlt(token="B", logprob=-2.0),
        TokenAlt(token=" the", logprob=-3.0),
    ]
    measured = dist_from_top(alts, letter_to_option, ["billing", "tech"])
    assert measured.selected == "billing"
    assert measured.truncated is True
    assert measured.missing_mass > 0


def test_sentinel_truncates() -> None:
    alts = [
        TokenAlt(token="A", logprob=SENTINEL_LOGPROB),
        TokenAlt(token="B", logprob=-0.2),
    ]
    measured = dist_from_top(alts, {"A": "a", "B": "b"}, ["a", "b"])
    assert measured.truncated is True
