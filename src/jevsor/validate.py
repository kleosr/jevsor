"""Request shape checks and 2-decimal distribution agreement."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from jevsor.contract import (
    MAX_CHOICE_OPTIONS,
    MAX_SCORE_LEVELS,
    MIN_CHOICE_OPTIONS,
    MIN_SCORE_LEVELS,
    ROUNDING,
    ChoiceQuestion,
    EvaluateRequest,
    NoulQuestion,
    Question,
    ScoreQuestion,
)
from jevsor.errors import ValidationError

# Per TypeSafe: values round to 2 decimals, so a K-way distribution may miss 1
# by up to 0.005 per mass point (half-ulp of the last digit).
SUM_TOLERANCE_PER_BIN = 0.005


def round2(value: float) -> float:
    return round(float(value), ROUNDING)


def distribution_tolerance(bin_count: int) -> float:
    return SUM_TOLERANCE_PER_BIN * bin_count + 1e-12


def parse_request(payload: EvaluateRequest | Mapping[str, Any]) -> EvaluateRequest:
    if isinstance(payload, EvaluateRequest):
        req = payload
    else:
        try:
            req = EvaluateRequest.model_validate(payload)
        except ValidationError:
            raise
        except Exception as exc:
            raise ValidationError(str(exc)) from exc
    validate_questions(req.questions)
    return req


def validate_questions(questions: Mapping[str, Question]) -> None:
    if not questions:
        raise ValidationError("questions map must be nonempty")
    for qid, question in questions.items():
        _validate_question(qid, question)


def _validate_question(qid: str, question: Question) -> None:
    if not question.instructions.strip():
        raise ValidationError(f"{qid}: instructions must be nonempty")
    if isinstance(question, ChoiceQuestion):
        n = len(question.criteria)
        if n < MIN_CHOICE_OPTIONS or n > MAX_CHOICE_OPTIONS:
            raise ValidationError(
                f"{qid}: choice criteria must have {MIN_CHOICE_OPTIONS}–{MAX_CHOICE_OPTIONS} options"
            )
        if any(not key for key in question.criteria):
            raise ValidationError(f"{qid}: choice option keys must be nonempty")
        return
    if isinstance(question, ScoreQuestion):
        n = len(question.criteria)
        if n < MIN_SCORE_LEVELS or n > MAX_SCORE_LEVELS:
            raise ValidationError(
                f"{qid}: score criteria must have {MIN_SCORE_LEVELS}–{MAX_SCORE_LEVELS} levels"
            )
        if any(not level.strip() for level in question.criteria):
            raise ValidationError(f"{qid}: score levels must be nonempty strings")
        return
    if isinstance(question, NoulQuestion) and question.criteria is not None:
        extra = set(question.criteria) - {"true", "false"}
        if extra:
            raise ValidationError(f"{qid}: noul criteria keys must be true/false, not {extra}")


def validate_distribution(
    probabilities: Mapping[str, float],
    *,
    expected_keys: Sequence[str] | None = None,
) -> dict[str, float]:
    if expected_keys is not None:
        missing = [k for k in expected_keys if k not in probabilities]
        extra = [k for k in probabilities if k not in expected_keys]
        if missing or extra:
            raise ValidationError(
                f"distribution keys mismatch: missing={missing} extra={extra}"
            )
    if not probabilities:
        raise ValidationError("distribution must be nonempty")
    rounded = {k: round2(v) for k, v in probabilities.items()}
    if any(v < 0 or v > 1 for v in rounded.values()):
        raise ValidationError("probabilities must lie in [0, 1]")
    total = sum(rounded.values())
    tol = distribution_tolerance(len(rounded))
    if abs(total - 1.0) > tol:
        raise ValidationError(
            f"probabilities sum to {total}, outside 1 ± {tol:.3f} (2-decimal rounding)"
        )
    return rounded


def weighted_score(probabilities: Mapping[str, float], levels: Sequence[str]) -> float:
    """0-based expected level index, rounded to 2 decimals."""
    if len(probabilities) != len(levels):
        raise ValidationError("score probabilities must cover every level")
    total = 0.0
    for index, level in enumerate(levels):
        total += index * probabilities[level]
    return round2(total)


def validate_noul(value: float) -> float:
    rounded = round2(value)
    if rounded < 0 or rounded > 1:
        raise ValidationError(f"noul must lie in [0, 1], got {rounded}")
    return rounded
