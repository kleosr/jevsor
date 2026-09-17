"""Deterministic post-model policy. Thresholds and disagreement live here, not in prompts."""

from __future__ import annotations

from typing import Any, Literal, Mapping

from jevsor.confidence import Band, raw_margin, route_band
from jevsor.contract import Answer, ChoiceAnswer, NoulAnswer, ScoreAnswer

Decision = Literal["proceed", "confirm", "human"]
BAND_RANK = {"act": 0, "confirm": 1, "human": 2}
BAND_TO_DECISION: dict[Band, Decision] = {
    "act": "proceed",
    "confirm": "confirm",
    "human": "human",
}

EscalateMode = Literal[False, True, "confirm", "human"]


class Gate:
    """Optional predicate over a sibling answer. Missing fields mean “always”."""

    __slots__ = (
        "question",
        "equals",
        "noul_gte",
        "noul_lte",
        "score_gte",
        "score_lte",
        "band",
    )

    def __init__(
        self,
        *,
        question: str | None = None,
        equals: str | None = None,
        noul_gte: float | None = None,
        noul_lte: float | None = None,
        score_gte: float | None = None,
        score_lte: float | None = None,
        band: Band | None = None,
    ) -> None:
        self.question = question
        self.equals = equals
        self.noul_gte = noul_gte
        self.noul_lte = noul_lte
        self.score_gte = score_gte
        self.score_lte = score_lte
        self.band = band

    def is_unconditional(self) -> bool:
        return self.question is None


def parse_gate(raw: Any) -> Gate:
    if raw is None:
        return Gate()
    if isinstance(raw, Gate):
        return raw
    if not isinstance(raw, Mapping):
        raise ValueError("gate must be an object")
    band = raw.get("band")
    if band is not None and band not in {"act", "confirm", "human"}:
        raise ValueError(f"unknown gate band {band!r}")
    question = raw.get("question") or raw.get("qid")
    return Gate(
        question=str(question) if question else None,
        equals=None if raw.get("equals") is None else str(raw.get("equals")),
        noul_gte=_opt_float(raw.get("noul_gte")),
        noul_lte=_opt_float(raw.get("noul_lte")),
        score_gte=_opt_float(raw.get("score_gte")),
        score_lte=_opt_float(raw.get("score_lte")),
        band=band,
    )


def _opt_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def noul_certainty(noul: float) -> float:
    """Map P(yes) onto [0, 1] peakedness. 0.5 → 0, 0 or 1 → 1. Not TypeSafe's formula."""
    return round(min(1.0, max(0.0, abs(float(noul) - 0.5) * 2.0)), 2)


def answer_certainty(answer: Answer) -> float:
    if isinstance(answer, NoulAnswer):
        return noul_certainty(answer.noul)
    return float(answer.confidence)


def answer_band(answer: Answer, *, low: float = 0.5, high: float = 0.8) -> Band:
    return route_band(answer_certainty(answer), low=low, high=high)


def gate_satisfied(
    gate: Gate,
    answers: Mapping[str, Answer],
    *,
    low: float = 0.5,
    high: float = 0.8,
) -> bool:
    if gate.is_unconditional():
        return True
    if gate.question is None or gate.question not in answers:
        return False
    answer = answers[gate.question]
    if gate.equals is not None:
        if not isinstance(answer, ChoiceAnswer) or answer.choice != gate.equals:
            return False
    if gate.noul_gte is not None:
        if not isinstance(answer, NoulAnswer) or answer.noul < gate.noul_gte:
            return False
    if gate.noul_lte is not None:
        if not isinstance(answer, NoulAnswer) or answer.noul > gate.noul_lte:
            return False
    if gate.score_gte is not None:
        if not isinstance(answer, ScoreAnswer) or answer.score < gate.score_gte:
            return False
    if gate.score_lte is not None:
        if not isinstance(answer, ScoreAnswer) or answer.score > gate.score_lte:
            return False
    if gate.band is not None and answer_band(answer, low=low, high=high) != gate.band:
        return False
    return True


def select_speculative(
    speculative: Mapping[str, Any],
    gates: Mapping[str, Gate],
    answers: Mapping[str, Answer],
    *,
    low: float = 0.5,
    high: float = 0.8,
) -> tuple[list[str], list[str]]:
    """Return (run_ids, skipped_ids) for isolated speculative heads."""
    run: list[str] = []
    skipped: list[str] = []
    for qid in speculative:
        gate = gates.get(qid) or Gate()
        if gate_satisfied(gate, answers, low=low, high=high):
            run.append(qid)
        else:
            skipped.append(qid)
    return run, skipped


def select_escalation(
    answers: Mapping[str, Answer],
    mode: EscalateMode | list[str],
    *,
    low: float = 0.5,
    high: float = 0.8,
) -> list[str]:
    if mode is False:
        return []
    if isinstance(mode, list):
        return [qid for qid in mode if qid in answers]
    want_confirm = mode is True or mode == "confirm"
    selected: list[str] = []
    for qid, answer in answers.items():
        band = answer_band(answer, low=low, high=high)
        if band == "human" or (want_confirm and band == "confirm"):
            selected.append(qid)
    return selected


def answers_disagree(left: Answer, right: Answer) -> bool:
    """Argmax / magnitude disagreement. Never averages distributions."""
    if type(left) is not type(right):
        return True
    if isinstance(left, ChoiceAnswer) and isinstance(right, ChoiceAnswer):
        return left.choice != right.choice
    if isinstance(left, ScoreAnswer) and isinstance(right, ScoreAnswer):
        return abs(left.score - right.score) > 0.5
    if isinstance(left, NoulAnswer) and isinstance(right, NoulAnswer):
        return abs(left.noul - right.noul) > 0.25
    return True


def _ranked(
    probabilities: Mapping[str, float],
    selected: str | None = None,
) -> tuple[str | None, str | None, float]:
    ordered = sorted(probabilities.items(), key=lambda item: item[1], reverse=True)
    if selected is None:
        winner = ordered[0][0] if ordered else None
        runner_up = ordered[1][0] if len(ordered) > 1 else None
        return winner, runner_up, raw_margin(probabilities)
    rest = [(key, mass) for key, mass in ordered if key != selected]
    runner_up = rest[0][0] if rest else None
    winner_mass = float(probabilities[selected]) if selected in probabilities else 0.0
    if not rest:
        return selected, None, round(winner_mass, 4)
    return selected, runner_up, round(winner_mass - float(rest[0][1]), 4)


def _head_route(
    answer: Answer,
    *,
    low: float,
    high: float,
    disagreed: bool,
) -> dict[str, Any]:
    band = answer_band(answer, low=low, high=high)
    if disagreed:
        band = "human"
    row: dict[str, Any] = {
        "type": answer.type,
        "band": band,
        "certainty": answer_certainty(answer),
        "provenance": answer.provenance,
        "disagreed": disagreed,
    }
    if isinstance(answer, ChoiceAnswer):
        winner, runner_up, margin = _ranked(answer.probabilities, selected=answer.choice)
        row.update(
            {
                "choice": answer.choice,
                "winner": winner,
                "runner_up": runner_up,
                "margin": margin,
                "probabilities": dict(answer.probabilities),
            }
        )
    elif isinstance(answer, ScoreAnswer):
        winner, runner_up, margin = _ranked(answer.probabilities)
        row.update(
            {
                "score": answer.score,
                "winner": winner,
                "runner_up": runner_up,
                "margin": margin,
                "probabilities": dict(answer.probabilities),
            }
        )
    else:
        yes = float(answer.noul)
        probs = {"yes": yes, "no": round(1.0 - yes, 2)}
        winner, runner_up, margin = _ranked(probs)
        row.update(
            {
                "noul": answer.noul,
                "winner": winner,
                "runner_up": runner_up,
                "margin": margin,
                "probabilities": probs,
            }
        )
    return row


def worst_band(bands: list[Band]) -> Band:
    if not bands:
        return "human"
    return max(bands, key=lambda band: BAND_RANK[band])


def route_answers(
    answers: Mapping[str, Answer] | Mapping[str, Mapping[str, Any]],
    *,
    low: float = 0.5,
    high: float = 0.8,
    disagreed: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Per-head route map. Prefer `route_report` at the MCP boundary."""
    flagged = set(disagreed or [])
    routed: dict[str, dict[str, Any]] = {}
    for qid, raw in answers.items():
        routed[qid] = _head_route(
            _coerce_answer(raw),
            low=low,
            high=high,
            disagreed=qid in flagged,
        )
    return routed


def route_report(
    answers: Mapping[str, Answer] | Mapping[str, Mapping[str, Any]],
    *,
    low: float = 0.5,
    high: float = 0.8,
    disagreed: list[str] | None = None,
) -> dict[str, Any]:
    """Envelope the Cursor agent should consume. Thresholds stay here, not in prompts.

    `decision` is the worst head after disagreement flags:
    proceed (all act) | confirm (ask the user / gather more) | human.
    confirm is not a second agent and not `escalate` (that re-asks heads).
    """
    flagged = list(disagreed or [])
    routes = route_answers(answers, low=low, high=high, disagreed=flagged)
    bands: list[Band] = [row["band"] for row in routes.values()]
    worst = worst_band(bands)
    return {
        "decision": BAND_TO_DECISION[worst],
        "worst_band": worst,
        "thresholds": {"low": low, "high": high},
        "disagreed": flagged,
        "degrade": None,
        "routes": routes,
    }


def fail_closed(exc: BaseException, *, status: int | None = None) -> dict[str, Any]:
    """MCP/agent fallback: never invent a distribution. Decision is human."""
    code = status if status is not None else int(getattr(exc, "status", 500) or 500)
    if code == 401:
        reason = "auth"
    elif code == 422:
        reason = "invalid"
    elif code == 429:
        reason = "rate_limited"
    elif code in {502, 503, 504, 529}:
        reason = "provider"
    else:
        reason = "error"
    return {
        "error": str(exc),
        "status": code,
        "decision": "human",
        "worst_band": "human",
        "degrade": "human",
        "reason": reason,
        "disagreed": [],
        "routes": {},
        "thresholds": {"low": 0.5, "high": 0.8},
    }


def _coerce_answer(raw: Answer | Mapping[str, Any]) -> Answer:
    if isinstance(raw, (ChoiceAnswer, ScoreAnswer, NoulAnswer)):
        return raw
    kind = str(raw.get("type", ""))
    if kind == "choice":
        return ChoiceAnswer.model_validate(raw)
    if kind == "score":
        return ScoreAnswer.model_validate(raw)
    if kind == "noul":
        return NoulAnswer.model_validate(raw)
    raise ValueError(f"cannot route answer type {kind!r}")
