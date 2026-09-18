from __future__ import annotations

from types import SimpleNamespace

from evals.cursor_bench import MODELS, pick_winner, score_answer
from jevsor.providers.cursor_agent import _model_payload


def test_score_choice_and_noul() -> None:
    assert score_answer(SimpleNamespace(choice="billing"), {"choice": "billing"})
    assert not score_answer(SimpleNamespace(choice="tech"), {"choice": "billing"})
    assert score_answer(SimpleNamespace(noul=0.71), {"noul_true": True})
    assert score_answer(SimpleNamespace(noul=0.2), {"noul_true": False})
    assert score_answer(SimpleNamespace(score=2.1), {"score_min": 2})
    assert score_answer(SimpleNamespace(score=0.4), {"score_max": 0.5})


def test_pick_winner_trades_one_miss_for_speed() -> None:
    rows = [
        {"model": "slow-perfect", "ok": True, "accuracy": 1.0, "median_ms": 8000, "n_questions": 9},
        {"model": "fast-close", "ok": True, "accuracy": 0.8889, "median_ms": 900, "n_questions": 9},
        {"model": "dead", "ok": False, "accuracy": 0.0, "median_ms": 10, "n_questions": 9},
    ]
    pick = pick_winner(rows)
    assert pick["best_quality"] == "slow-perfect"
    assert pick["fastest"] == "fast-close"
    assert pick["recommended"] == "fast-close"


def test_live_model_tokens_parse() -> None:
    for name in MODELS:
        payload = _model_payload(name)
        assert payload["id"] in {"composer-2.5", "grok-4.6"}
        assert payload.get("params")
