"""Latency-aware schedule. Pure functions; the runner owns I/O."""

from __future__ import annotations

from typing import Literal

from jevsor.capabilities import WIDE_CHOICE
from jevsor.contract import Question
from jevsor.letter import letter_ok

RequestedFanout = Literal["auto", "batch", "isolated"]
ResolvedFanout = Literal["batch", "isolated"]


def resolve_fanout(
    requested: RequestedFanout,
    *,
    measured: bool,
    questions: dict[str, Question] | None = None,
) -> ResolvedFanout:
    """Map caller intent onto a feasible LLM schedule.

    Jev's sampler evaluates every head in one forward pass. We do not have that
    sampler. For logprob models, independent single-token heads are isolated
    calls. For prompted models, one JSON object is the cheap analogue of
    speculative fan-out.
    """
    del questions
    if requested == "isolated":
        return "isolated"
    if measured:
        return "isolated"
    return "batch"


def can_measure_all(questions: dict[str, Question]) -> bool:
    return all(letter_ok(q, WIDE_CHOICE) for q in questions.values())
