"""Jev-compatible request/answer types. Keys are ids only — never sent to the model."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_CHOICE_OPTIONS = 255
MIN_CHOICE_OPTIONS = 2
MIN_SCORE_LEVELS = 2
MAX_SCORE_LEVELS = 10
ROUNDING = 2


class ChoiceQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["choice"] = "choice"
    instructions: str
    criteria: dict[str, str | None]


class ScoreQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["score"] = "score"
    instructions: str
    criteria: list[str]


class NoulQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["noul", "boolean"] = "noul"
    instructions: str
    criteria: dict[str, str | None] | None = None


Question = ChoiceQuestion | ScoreQuestion | NoulQuestion


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0

    def plus(self, other: Usage) -> Usage:
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )


class ChoiceAnswer(BaseModel):
    type: Literal["choice"] = "choice"
    choice: str
    probabilities: dict[str, float]
    confidence: float
    provenance: Literal["measured", "prompted"]
    truncated: bool = False
    missing_mass: float = 0.0


class ScoreAnswer(BaseModel):
    type: Literal["score"] = "score"
    score: float
    probabilities: dict[str, float]
    confidence: float
    provenance: Literal["measured", "prompted"]
    truncated: bool = False
    missing_mass: float = 0.0


class NoulAnswer(BaseModel):
    type: Literal["noul"] = "noul"
    noul: float
    provenance: Literal["measured", "prompted"]
    truncated: bool = False
    missing_mass: float = 0.0

    @property
    def probability(self) -> float:
        return self.noul


Answer = ChoiceAnswer | ScoreAnswer | NoulAnswer


class QuestionDebug(BaseModel):
    mode: str
    provenance: Literal["measured", "prompted"]
    attempts: int = 1
    temperature: float = 0.0
    seed: int | None = None
    truncated: bool = False


class Debug(BaseModel):
    provider: str
    model: str
    jevsor_version: str
    fanout: Literal["batch", "isolated"]
    requested_fanout: str | None = None
    mixed_provenance: bool = False
    second_harness: bool = False
    escalated: list[str] = Field(default_factory=list)
    skipped_speculative: list[str] = Field(default_factory=list)
    disagreed: list[str] = Field(default_factory=list)
    verified: list[str] = Field(default_factory=list)
    measured: bool = False
    questions: dict[str, QuestionDebug] = Field(default_factory=dict)


class Response(BaseModel):
    model: str
    answers: dict[str, Answer]
    usage: Usage
    mixed_provenance: bool = False
    debug: Debug | None = None


class EvaluateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")
    state: Any = None
    questions: dict[str, Question]
    model: str | None = None

    @model_validator(mode="after")
    def nonempty_questions(self) -> EvaluateRequest:
        if not self.questions:
            raise ValueError("questions map must be nonempty")
        return self


def Choice(instructions: str, criteria: dict[str, str | None]) -> ChoiceQuestion:
    return ChoiceQuestion(instructions=instructions, criteria=criteria)


def Score(instructions: str, criteria: list[str]) -> ScoreQuestion:
    return ScoreQuestion(instructions=instructions, criteria=criteria)


def Noul(
    instructions: str,
    criteria: dict[str, str | None] | None = None,
) -> NoulQuestion:
    return NoulQuestion(type="noul", instructions=instructions, criteria=criteria)


def Boolean(
    instructions: str,
    criteria: dict[str, str | None] | None = None,
) -> NoulQuestion:
    return NoulQuestion(type="boolean", instructions=instructions, criteria=criteria)
