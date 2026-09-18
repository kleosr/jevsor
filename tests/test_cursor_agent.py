from __future__ import annotations

from jevsor.providers.cursor_agent import _model_payload


def test_model_payload_plain_id() -> None:
    assert _model_payload("grok-4.6") == {"id": "grok-4.6"}


def test_model_payload_composer_fast_boolean() -> None:
    assert _model_payload("composer-2.5:fast") == {
        "id": "composer-2.5",
        "params": [{"id": "fast", "value": "true"}],
    }
    assert _model_payload("composer-2.5:fast=false") == {
        "id": "composer-2.5",
        "params": [{"id": "fast", "value": "false"}],
    }


def test_model_payload_grok_effort_aliases() -> None:
    assert _model_payload("grok-4.6:low") == {
        "id": "grok-4.6",
        "params": [{"id": "effort", "value": "low"}],
    }
    assert _model_payload("grok-4.6:extra-high") == {
        "id": "grok-4.6",
        "params": [{"id": "effort", "value": "xhigh"}],
    }
    assert _model_payload("grok-4.6:effort=xhigh") == {
        "id": "grok-4.6",
        "params": [{"id": "effort", "value": "xhigh"}],
    }
    assert _model_payload("grok-4.6:high:fast") == {
        "id": "grok-4.6",
        "params": [
            {"id": "effort", "value": "high"},
            {"id": "fast", "value": "true"},
        ],
    }
