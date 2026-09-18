"""Post-hoc temperature scaling. Opt-in; never silent calibration theater.

Softmax(log p / T) does not change argmax. It cannot raise top-1 accuracy.
Use it only to reshape a measured distribution for ECE / NLL. Inverse-entropy
confidence is a routing statistic, not P(winner) — score ECE on max mass.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from jevsor.confidence import confidence_from_distribution
from jevsor.contract import Answer, ChoiceAnswer, NoulAnswer, ScoreAnswer
from jevsor.errors import ValidationError
from jevsor.validate import round2, validate_distribution, validate_noul, weighted_score


def rescale_answer(answer: Answer, temperature: float | None) -> Answer:
    """Apply T to a measured distribution. Prompted answers are left alone."""
    if temperature is None or abs(temperature - 1.0) < 1e-9:
        return answer
    if answer.provenance != "measured":
        return answer
    if isinstance(answer, NoulAnswer):
        scaled = scale_distribution({"yes": answer.noul, "no": round2(1.0 - answer.noul)}, temperature)
        return answer.model_copy(update={"noul": validate_noul(scaled["yes"])})
    if isinstance(answer, ChoiceAnswer):
        probs = scale_distribution(answer.probabilities, temperature)
        return answer.model_copy(
            update={
                "probabilities": probs,
                "choice": answer.choice,
                "confidence": confidence_from_distribution(probs),
            }
        )
    if isinstance(answer, ScoreAnswer):
        levels = list(answer.probabilities)
        probs = scale_distribution(answer.probabilities, temperature)
        return answer.model_copy(
            update={
                "probabilities": probs,
                "score": weighted_score(probs, levels),
                "confidence": confidence_from_distribution(probs),
            }
        )
    return answer


def scale_distribution(
    probabilities: Mapping[str, float],
    temperature: float,
) -> dict[str, float]:
    """Softmax(log p / T). T→0 sharpens; T→∞ flattens. Does not invent mass."""
    if temperature <= 0:
        raise ValueError("temperature must be > 0")
    keys = list(probabilities)
    if not keys:
        raise ValueError("distribution must be nonempty")
    logs = [math.log(max(float(probabilities[k]), 1e-12)) / temperature for k in keys]
    peak = max(logs)
    exps = [math.exp(v - peak) for v in logs]
    z = sum(exps) or 1.0
    values = [round2(e / z) for e in exps]
    values[-1] = round2(1.0 - sum(values[:-1]))
    scaled = {k: max(0.0, min(1.0, v)) for k, v in zip(keys, values, strict=True)}
    return validate_distribution(scaled, expected_keys=keys)


def nll_label(probabilities: Mapping[str, float], label: str) -> float:
    p = min(1.0 - 1e-12, max(1e-12, float(probabilities.get(label, 0.0))))
    return -math.log(p)


def fit_distribution_temperature(
    rows: Sequence[tuple[Mapping[str, float], str]],
    *,
    lo: float = 0.05,
    hi: float = 5.0,
    step: float = 0.05,
) -> float:
    """Grid-search T on labeled distributions. Report only — caller applies."""
    if not rows:
        return 1.0
    best_t = 1.0
    best = float("inf")
    t = lo
    while t <= hi + 1e-12:
        loss = 0.0
        for probs, label in rows:
            try:
                loss += nll_label(scale_distribution(probs, t), label)
            except (ValidationError, ValueError):
                loss = float("inf")
                break
        loss /= len(rows)
        if loss < best:
            best = loss
            best_t = t
        t = round(t + step, 10)
    return round(best_t, 4)
