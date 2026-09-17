from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from jevsor.contract import Boolean, Choice, Noul, Score
from jevsor.errors import ValidationError
from jevsor.validate import parse_request

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _schema(name: str) -> dict:
    return json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))


def test_golden_request_matches_schema() -> None:
    payload = json.loads((FIXTURES / "golden_request.json").read_text(encoding="utf-8"))
    req = parse_request(payload)
    assert set(req.questions) == {"department", "frustration", "is_urgent"}
    Draft202012Validator(_schema("choice.json")).validate(payload["questions"]["department"])
    Draft202012Validator(_schema("score.json")).validate(payload["questions"]["frustration"])
    Draft202012Validator(_schema("boolean.json")).validate(payload["questions"]["is_urgent"])


def test_golden_response_matches_schema() -> None:
    payload = json.loads((FIXTURES / "golden_response.json").read_text(encoding="utf-8"))
    Draft202012Validator(_schema("response.json")).validate(payload)
    assert payload["answers"]["is_urgent"]["noul"] == 0.92


def test_route_report_matches_schema() -> None:
    from jevsor.policy import fail_closed, route_report

    report = route_report(
        {
            "department": payload_choice(),
            "is_urgent": {"type": "noul", "noul": 0.92, "provenance": "prompted"},
        }
    )
    Draft202012Validator(_schema("route.json")).validate(report)
    closed = fail_closed(Exception("down"), status=502)
    Draft202012Validator(_schema("route.json")).validate(closed)


def payload_choice() -> dict:
    return {
        "type": "choice",
        "choice": "billing",
        "probabilities": {"billing": 0.9, "tech": 0.1},
        "confidence": 0.81,
        "provenance": "prompted",
    }


def test_helpers_build_questions() -> None:
    q = Choice("Which team?", {"billing": "money", "tech": None})
    assert q.type == "choice"
    assert Score("rate", ["a", "b"]).type == "score"
    assert Noul("urgent?").type == "noul"
    assert Boolean("urgent?").type == "boolean"


def test_noul_alias_accepted() -> None:
    req = parse_request({
        "state": None,
        "questions": {"u": {"type": "noul", "instructions": "Urgent?"}},
    })
    assert req.questions["u"].type == "noul"


def test_boolean_alias_accepted() -> None:
    req = parse_request({
        "state": "x",
        "questions": {"u": {"type": "boolean", "instructions": "Urgent?"}},
    })
    assert req.questions["u"].type == "boolean"


def test_empty_questions_rejected() -> None:
    with pytest.raises(ValidationError):
        parse_request({"state": "x", "questions": {}})


def test_null_state_ok() -> None:
    req = parse_request({"state": None, "questions": {"u": Noul("Urgent?")}})
    assert req.state is None


def test_choice_bounds() -> None:
    with pytest.raises(ValidationError):
        parse_request({"questions": {"q": Choice("x", {"only": "one"})}})
    too_many = {str(i): None for i in range(256)}
    with pytest.raises(ValidationError):
        parse_request({"questions": {"q": Choice("x", too_many)}})


def test_score_bounds() -> None:
    with pytest.raises(ValidationError):
        parse_request({"questions": {"q": Score("x", ["only"])}})
    with pytest.raises(ValidationError):
        parse_request({"questions": {"q": Score("x", [str(i) for i in range(11)])}})


def test_unknown_field_on_question_rejected() -> None:
    with pytest.raises(ValidationError):
        parse_request({
            "questions": {
                "q": {"type": "noul", "instructions": "x", "surprise": True},
            }
        })


def test_question_keys_round_trip() -> None:
    req = parse_request({
        "questions": {
            "dept": Choice("Which?", {"a": None, "b": None}),
            "urg": Noul("Urgent?"),
        }
    })
    assert list(req.questions) == ["dept", "urg"]
