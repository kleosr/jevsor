"""Single-token letter/digit matching over top_logprobs. No tokenizer dependency."""

from __future__ import annotations

import math
from dataclasses import dataclass

SENTINEL_LOGPROB = -9999.0
ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
DIGITS = "0123456789"
YES_NO = ("Y", "N")
TOP_K_CAP = 20


@dataclass(frozen=True)
class TokenAlt:
    token: str
    logprob: float


@dataclass(frozen=True)
class MeasuredDist:
    probabilities: dict[str, float]
    truncated: bool
    missing_mass: float
    selected: str


def letter_for_index(index: int) -> str:
    if index < 0 or index >= len(ALPHABET):
        raise ValueError(f"letter index {index} exceeds A–Z alphabet")
    return ALPHABET[index]


def option_letters(keys: list[str]) -> dict[str, str]:
    if len(keys) > len(ALPHABET):
        raise ValueError("letter mode supports at most 26 options")
    return {key: letter_for_index(i) for i, key in enumerate(keys)}


def canonicalize_token(token: str) -> str:
    return token.replace("Ġ", " ").replace("▁", " ").strip().upper()


def match_option(token: str, letter_to_option: dict[str, str]) -> str | None:
    canon = canonicalize_token(token)
    if not canon:
        return None
    letter = canon[0]
    return letter_to_option.get(letter)


def softmax(logprobs: list[float]) -> list[float]:
    finite = [lp for lp in logprobs if lp > SENTINEL_LOGPROB / 2]
    if not finite:
        return [0.0] * len(logprobs)
    peak = max(finite)
    exps = [math.exp(lp - peak) if lp > SENTINEL_LOGPROB / 2 else 0.0 for lp in logprobs]
    z = sum(exps)
    if z <= 0:
        return [0.0] * len(logprobs)
    return [e / z for e in exps]


def dist_from_top(
    alts: list[TokenAlt],
    letter_to_option: dict[str, str],
    option_keys: list[str],
) -> MeasuredDist:
    """Map top-k token alts onto options. Unmatched mass is missing, never guessed."""
    saw_sentinel = any(alt.logprob <= SENTINEL_LOGPROB / 2 for alt in alts)
    option_lp: dict[str, float] = {}
    matched_exp = 0.0
    total_exp = 0.0
    seen: set[str] = set()
    peak = max((alt.logprob for alt in alts if alt.logprob > SENTINEL_LOGPROB / 2), default=0.0)
    for alt in alts:
        if alt.logprob <= SENTINEL_LOGPROB / 2:
            continue
        mass = math.exp(alt.logprob - peak)
        total_exp += mass
        option = match_option(alt.token, letter_to_option)
        if option is None or option in seen:
            continue
        seen.add(option)
        option_lp[option] = alt.logprob
        matched_exp += mass
    missing = 0.0 if total_exp <= 0 else max(0.0, 1.0 - (matched_exp / total_exp))
    truncated = saw_sentinel or missing > 1e-6 or len(option_lp) < len(option_keys)
    logs = [option_lp.get(key, SENTINEL_LOGPROB) for key in option_keys]
    masses = softmax(logs)
    covered = 1.0 - missing
    probabilities = {
        key: round(mass * covered, 4) for key, mass in zip(option_keys, masses, strict=True)
    }
    if not any(probabilities.values()):
        # No option token appeared. Uniform leftover, fully truncated.
        uniform = round(1.0 / len(option_keys), 4)
        probabilities = {key: uniform for key in option_keys}
        missing = 1.0
        truncated = True
    selected = max(probabilities, key=lambda k: probabilities[k])
    return MeasuredDist(
        probabilities=probabilities,
        truncated=truncated,
        missing_mass=round(missing, 4),
        selected=selected,
    )


def noul_from_yes_no(alts: list[TokenAlt]) -> MeasuredDist:
    mapping = {"Y": "yes", "N": "no"}
    return dist_from_top(alts, mapping, ["yes", "no"])


def letter_ok(question: object, wide_limit: int) -> bool:
    from jevsor.contract import ChoiceQuestion, NoulQuestion, ScoreQuestion

    if isinstance(question, ChoiceQuestion):
        try:
            option_letters(list(question.criteria))
        except ValueError:
            return False
        return len(question.criteria) <= wide_limit
    return isinstance(question, (ScoreQuestion, NoulQuestion))
