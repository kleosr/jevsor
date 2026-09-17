"""Turn a completion into a typed answer. Shared by measured and prompted paths."""

from __future__ import annotations

from typing import Any

from jevsor.confidence import confidence_from_distribution
from jevsor.contract import (
    Answer,
    ChoiceAnswer,
    ChoiceQuestion,
    NoulAnswer,
    NoulQuestion,
    Question,
    ScoreAnswer,
    ScoreQuestion,
)
from jevsor.errors import ValidationError
from jevsor.letter import TokenAlt as LetterAlt
from jevsor.letter import dist_from_top, noul_from_yes_no
from jevsor.providers.base import Completion
from jevsor.validate import round2, validate_distribution, validate_noul, weighted_score


def measured_answer(question: Question, completion: Completion, mapping: dict[str, str]) -> Answer:
    if completion.refusal:
        raise ValidationError(f"model refused: {completion.refusal}")
    if not completion.token_alts:
        raise ValidationError("logprobs missing from completion")
    alts = [LetterAlt(token=a.token, logprob=a.logprob) for a in completion.token_alts[0]]
    if isinstance(question, NoulQuestion):
        measured = noul_from_yes_no(alts)
        return NoulAnswer(
            noul=validate_noul(measured.probabilities.get("yes", 0.0)),
            provenance="measured",
            truncated=measured.truncated,
            missing_mass=measured.missing_mass,
        )
    if isinstance(question, ChoiceQuestion):
        letter_to_option = {letter: key for key, letter in mapping.items()}
        keys = list(question.criteria)
        measured = dist_from_top(alts, letter_to_option, keys)
        probs = validate_distribution(measured.probabilities, expected_keys=keys)
        return ChoiceAnswer(
            choice=measured.selected,
            probabilities=probs,
            confidence=confidence_from_distribution(probs),
            provenance="measured",
            truncated=measured.truncated,
            missing_mass=measured.missing_mass,
        )
    if isinstance(question, ScoreQuestion):
        digit_to_level = {str(i): level for i, level in enumerate(question.criteria)}
        levels = list(question.criteria)
        measured = dist_from_top(alts, digit_to_level, levels)
        probs = validate_distribution(measured.probabilities, expected_keys=levels)
        return ScoreAnswer(
            score=weighted_score(probs, levels),
            probabilities=probs,
            confidence=confidence_from_distribution(probs),
            provenance="measured",
            truncated=measured.truncated,
            missing_mass=measured.missing_mass,
        )
    raise ValidationError("unknown question type")


def prompted_answer(question: Question, payload: dict[str, Any]) -> Answer:
    if isinstance(question, NoulQuestion):
        raw = payload.get("noul", payload.get("probability"))
        if raw is None:
            raise ValidationError("prompted noul missing")
        return NoulAnswer(noul=validate_noul(float(raw)), provenance="prompted")
    if isinstance(question, ChoiceQuestion):
        keys = list(question.criteria)
        probs = payload.get("probabilities")
        if not probs:
            choice = payload.get("choice")
            if choice not in keys:
                raise ValidationError("prompted choice missing probabilities")
            probs = {key: (1.0 if key == choice else 0.0) for key in keys}
        probs = validate_distribution(probs, expected_keys=keys)
        choice = payload.get("choice") or max(probs, key=lambda k: probs[k])
        if choice not in probs:
            raise ValidationError(f"choice {choice!r} not in criteria")
        return ChoiceAnswer(
            choice=str(choice),
            probabilities=probs,
            confidence=confidence_from_distribution(probs),
            provenance="prompted",
        )
    if isinstance(question, ScoreQuestion):
        levels = list(question.criteria)
        probs = payload.get("probabilities")
        if not probs:
            if payload.get("score") is None:
                raise ValidationError("prompted score missing probabilities")
            idx = min(max(int(round(float(payload["score"]))), 0), len(levels) - 1)
            probs = {level: (1.0 if i == idx else 0.0) for i, level in enumerate(levels)}
        probs = validate_distribution(probs, expected_keys=levels)
        score = payload.get("score")
        expected = weighted_score(probs, levels)
        if score is not None and abs(round2(float(score)) - expected) > 0.05 * len(levels):
            score = expected
        else:
            score = expected if score is None else round2(float(score))
        return ScoreAnswer(
            score=score,
            probabilities=probs,
            confidence=confidence_from_distribution(probs),
            provenance="prompted",
        )
    raise ValidationError("unknown question type")


def extract_answers_blob(parsed: Any, questions: dict[str, Question] | int) -> dict[str, Any]:
    if not isinstance(parsed, dict):
        raise ValidationError("prompted output is not an object")
    keys = None if isinstance(questions, int) else list(questions)
    n_questions = questions if isinstance(questions, int) else len(keys or [])
    raw = parsed["answers"] if isinstance(parsed.get("answers"), dict) else parsed
    if not isinstance(raw, dict):
        raise ValidationError("prompted output missing answers map")
    if keys is None:
        return raw
    if n_questions == 1:
        key = keys[0]
        if key in raw and not any(k in raw for k in ("choice", "noul", "score", "probabilities")):
            return {key: _coerce_payload(raw[key], questions[key])}
        if any(k in raw for k in ("choice", "noul", "score", "probabilities", "type")):
            return {key: _coerce_payload(raw, questions[key])}
    if set(raw) >= set(keys):
        return {key: _coerce_payload(raw[key], questions[key]) for key in keys}
    mapped: dict[str, Any] = {}
    values = list(raw.values())
    for index, key in enumerate(keys):
        item = raw.get(key) or raw.get(f"Q{index + 1}") or raw.get(f"q{index + 1}")
        if item is None and len(values) == n_questions:
            item = values[index]
        if item is None:
            raise ValidationError("prompted output missing answers map")
        mapped[key] = _coerce_payload(item, questions[key])
    return mapped


def _coerce_payload(item: Any, question: Question) -> dict[str, Any]:
    if isinstance(item, dict):
        if any(k in item for k in ("probabilities", "choice", "noul", "score")):
            return item
        if item and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in item.values()):
            return _dist_payload(item, question)
        return item
    if isinstance(question, ChoiceQuestion) and isinstance(item, str):
        return {"choice": item}
    if isinstance(question, ScoreQuestion) and isinstance(item, (int, float)):
        return {"score": float(item)}
    if isinstance(question, NoulQuestion):
        if isinstance(item, bool):
            return {"noul": 1.0 if item else 0.0}
        if isinstance(item, (int, float)):
            return {"noul": float(item)}
        if isinstance(item, str) and item.lower() in {"yes", "y", "true"}:
            return {"noul": 1.0}
        if isinstance(item, str) and item.lower() in {"no", "n", "false"}:
            return {"noul": 0.0}
    raise ValidationError("prompted answer is not an object")


def _dist_payload(item: dict[str, Any], question: Question) -> dict[str, Any]:
    if isinstance(question, ChoiceQuestion):
        return {"probabilities": item}
    if isinstance(question, ScoreQuestion):
        levels = list(question.criteria)
        mapped: dict[str, Any] = {}
        for key, value in item.items():
            if key in levels:
                mapped[key] = value
            elif str(key).isdigit() and int(key) < len(levels):
                mapped[levels[int(key)]] = value
        return {"probabilities": mapped or item}
    if isinstance(question, NoulQuestion):
        lowered = {str(k).lower(): float(v) for k, v in item.items()}
        if "yes" in lowered:
            return {"noul": lowered["yes"]}
        if "true" in lowered:
            return {"noul": lowered["true"]}
        if "1" in lowered and "0" in lowered and len(lowered) == 2:
            return {"noul": lowered["1"]}
        if "0" in lowered:
            return {"noul": max(0.0, min(1.0, 1.0 - lowered["0"]))}
        return {"noul": max(lowered.values())}
    return {"probabilities": item}
