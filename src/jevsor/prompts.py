"""Prompt and JSON-schema builders. Question keys stay out of model-facing text."""

from __future__ import annotations

import json
from typing import Any

from jevsor.contract import ChoiceQuestion, NoulQuestion, Question, ScoreQuestion
from jevsor.letter import option_letters


SYSTEM = (
    "You are a decision head. Answer only with the requested token or JSON. "
    "Do not explain. Judge the state using the rubric. "
    "Question names are withheld on purpose."
)


def state_block(state: Any) -> str:
    if state is None:
        return "(no state)"
    if isinstance(state, str):
        return state
    return json.dumps(state, ensure_ascii=False)


def letter_prompt(state: Any, question: Question) -> tuple[str, dict[str, str]]:
    body = [SYSTEM, "", "State:", state_block(state), "", "Question:", question.instructions]
    mapping: dict[str, str]
    if isinstance(question, ChoiceQuestion):
        keys = list(question.criteria)
        mapping = option_letters(keys)
        body.append("Options (reply with exactly one letter):")
        for key, letter in mapping.items():
            desc = question.criteria[key]
            extra = f" — {desc}" if desc else ""
            body.append(f"{letter} = {key}{extra}")
    elif isinstance(question, ScoreQuestion):
        mapping = {level: str(i) for i, level in enumerate(question.criteria)}
        body.append("Levels (reply with exactly one digit, 0 = first level):")
        for i, level in enumerate(question.criteria):
            body.append(f"{i} = {level}")
    else:
        mapping = {"yes": "Y", "no": "N"}
        true_c = (question.criteria or {}).get("true") if isinstance(question, NoulQuestion) else None
        false_c = (question.criteria or {}).get("false") if isinstance(question, NoulQuestion) else None
        body.append("Reply with exactly one letter: Y (yes) or N (no).")
        if true_c:
            body.append(f"Y = {true_c}")
        if false_c:
            body.append(f"N = {false_c}")
    return "\n".join(body), mapping


def prompted_schema(questions: dict[str, Question]) -> dict[str, Any]:
    props = {qid: _one_schema(q) for qid, q in questions.items()}
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["answers"],
        "properties": {
            "answers": {
                "type": "object",
                "additionalProperties": False,
                "required": list(questions),
                "properties": props,
            }
        },
    }


def _one_schema(question: Question) -> dict[str, Any]:
    if isinstance(question, ChoiceQuestion):
        keys = list(question.criteria)
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["type", "choice", "probabilities"],
            "properties": {
                "type": {"const": "choice"},
                "choice": {"type": "string", "enum": keys},
                "probabilities": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": keys,
                    "properties": {k: {"type": "number"} for k in keys},
                },
            },
        }
    if isinstance(question, ScoreQuestion):
        levels = list(question.criteria)
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["type", "score", "probabilities"],
            "properties": {
                "type": {"const": "score"},
                "score": {"type": "number"},
                "probabilities": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": levels,
                    "properties": {k: {"type": "number"} for k in levels},
                },
            },
        }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["type", "noul"],
        "properties": {
            "type": {"const": "noul"},
            "noul": {"type": "number", "minimum": 0, "maximum": 1},
        },
    }


def prompted_prompt(state: Any, questions: dict[str, Question]) -> str:
    lines = [
        SYSTEM,
        "",
        "State:",
        state_block(state),
        "",
        "Return JSON {\"answers\": {<id>: ...}} with a probability distribution for each question.",
        "Distributions must cover every option/level and sum to 1.",
        "Do not include the question ids in any rationale; ids are response keys only.",
        "",
    ]
    for i, (qid, question) in enumerate(questions.items(), start=1):
        del qid
        lines.append(f"Q{i}: {question.instructions}")
        if isinstance(question, ChoiceQuestion):
            for key, desc in question.criteria.items():
                extra = f" — {desc}" if desc else ""
                lines.append(f"  - {key}{extra}")
        elif isinstance(question, ScoreQuestion):
            for i, level in enumerate(question.criteria):
                lines.append(f"  - {i}: {level}")
        else:
            crit = question.criteria or {}
            if crit.get("true"):
                lines.append(f"  - yes: {crit['true']}")
            if crit.get("false"):
                lines.append(f"  - no: {crit['false']}")
        lines.append("")
    return "\n".join(lines)
