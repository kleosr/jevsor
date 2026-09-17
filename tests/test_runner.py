from __future__ import annotations

import json
from pathlib import Path

import pytest

from jevsor.capabilities import clear_probe_cache
from jevsor.contract import Choice, Noul, Score
from jevsor.errors import ProviderError, ValidationError
from jevsor.providers.base import Completion, TokenAlt
from jevsor.providers.stub import StubProvider
from jevsor.runner import Client

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(autouse=True)
def _reset_probe() -> None:
    clear_probe_cache()


def test_stub_evaluate_all_three_types() -> None:
    payload = json.loads((FIXTURES / "golden_request.json").read_text(encoding="utf-8"))
    with Client(provider="stub", model="stub", fanout="isolated") as client:
        response = client.evaluate(payload)
    assert set(response.answers) == {"department", "frustration", "is_urgent"}
    dept = response.answers["department"]
    assert dept.type == "choice"
    assert abs(sum(dept.probabilities.values()) - 1) < 0.05
    assert response.answers["frustration"].type == "score"
    assert 0 <= response.answers["is_urgent"].noul <= 1
    assert response.debug is not None
    assert response.debug.provider == "stub"


def test_aevaluate() -> None:
    import asyncio

    async def go() -> None:
        with Client("stub") as client:
            response = await client.aevaluate(state="x", questions={"u": Noul("Y?")})
        assert response.answers["u"].type == "noul"

    asyncio.run(go())


def test_helpers_keyword_api() -> None:
    with Client("stub") as client:
        response = client.evaluate(
            state="payouts failing",
            questions={
                "dept": Choice("Which team?", {"billing": "money", "tech": "bugs"}),
                "urg": Noul("Urgent?"),
            },
        )
    assert "dept" in response.answers
    assert response.answers["urg"].type == "noul"


def test_batch_prompted_when_no_logprobs() -> None:
    stub = StubProvider(logprobs=False)
    with Client(provider=stub, fanout="batch") as client:
        response = client.evaluate(
            state="hello",
            questions={"dept": Choice("Which?", {"a": None, "b": None})},
        )
    assert response.answers["dept"].provenance == "prompted"
    assert stub.calls >= 1


def test_probe_is_cached() -> None:
    stub = StubProvider(logprobs=True)
    with Client(provider=stub, fanout="isolated") as client:
        client.evaluate(state="x", questions={"u": Noul("Y?")})
        calls_after_first = stub.calls
        client.evaluate(state="y", questions={"u": Noul("Y?")})
    # Second evaluate should not re-probe (probe is one extra complete).
    assert stub.calls - calls_after_first == 1


def test_retry_then_success() -> None:
    stub = StubProvider(fail_times=1, fail_exc=ProviderError("boom", status=503), logprobs=False)
    with Client(provider=stub, fanout="batch") as client:
        response = client.evaluate(
            state="x",
            questions={"u": Noul("Y?")},
        )
    assert response.answers["u"].type == "noul"
    assert stub.calls >= 2


def test_isolated_all_or_nothing_cancels() -> None:
    stub = StubProvider(fail_times=5, fail_exc=ProviderError("boom", status=502))
    with Client(provider=stub, fanout="isolated", concurrency=1) as client:
        with pytest.raises(ProviderError):
            client.evaluate(
                state="x",
                questions={
                    "a": Noul("A?"),
                    "b": Noul("B?"),
                    "c": Noul("C?"),
                },
            )


def test_score_digit_path() -> None:
    with Client("stub", fanout="isolated") as client:
        response = client.evaluate(
            state="angry email",
            questions={"s": Score("frustration", ["Calm", "Mad", "Furious"])},
        )
    ans = response.answers["s"]
    assert ans.type == "score"
    assert 0 <= ans.score <= 2
    assert set(ans.probabilities) == {"Calm", "Mad", "Furious"}


def test_seed_and_temperature_plumbed() -> None:
    stub = StubProvider()
    with Client(provider=stub, fanout="isolated", temperature=0.0, seed=7) as client:
        client.evaluate(state="x", questions={"u": Noul("Y?")})
    assert stub.last_kwargs["temperature"] == 0.0
    assert stub.last_kwargs["seed"] == 7


def test_question_keys_not_in_letter_prompt() -> None:
    stub = StubProvider()
    with Client(provider=stub, fanout="isolated") as client:
        client.evaluate(
            state="ticket",
            questions={"secret_key": Choice("Which?", {"billing": "pay", "tech": "bug"})},
        )
    blob = json.dumps(stub.last_messages)
    assert "secret_key" not in blob


def test_mixed_provenance_flag() -> None:
    # Wide choice uses measured noul-per-option; prompted sibling would mix.
    stub = StubProvider(logprobs=True)
    many = {f"opt{i}": None for i in range(21)}
    with Client(provider=stub, fanout="isolated") as client:
        response = client.evaluate(
            state="x",
            questions={"wide": Choice("Pick", many)},
        )
    assert response.answers["wide"].truncated is True
    assert response.answers["wide"].type == "choice"


def test_scripted_space_token() -> None:
    prompt_contains = None

    class Capture(StubProvider):
        def complete(self, messages, **kwargs):  # type: ignore[no-untyped-def]
            nonlocal prompt_contains
            prompt_contains = messages[-1]["content"]
            return Completion(
                text="A",
                token_alts=[[TokenAlt(token=" A", logprob=-0.01), TokenAlt(token="B", logprob=-4.0)]],
                input_tokens=4,
                output_tokens=1,
            )

    stub = Capture()
    with Client(provider=stub, fanout="isolated") as client:
        response = client.evaluate(
            state="x",
            questions={"d": Choice("Which?", {"billing": None, "tech": None})},
        )
    assert response.answers["d"].choice == "billing"
    assert prompt_contains is not None
    assert "A = billing" in prompt_contains


def test_prompted_choice_without_probability_map() -> None:
    from jevsor.codecs import extract_answers_blob, prompted_answer

    ans = prompted_answer(
        Choice("Which?", {"billing": None, "tech": None}),
        {"type": "choice", "choice": "billing"},
    )
    assert ans.choice == "billing"
    assert ans.probabilities["billing"] == 1.0
    assert ans.provenance == "prompted"
    questions = {
        "dept": Choice("Which?", {"billing": None, "tech": None}),
        "urg": Noul("Urgent?"),
    }
    blob = extract_answers_blob(
        {
            "answers": {
                "Q1": {"billing": 0.88, "technical": 0.1, "sales": 0.02},
                "Q2": {"noul": 0.8},
            }
        },
        questions,
    )
    assert blob["dept"]["probabilities"]["billing"] == 0.88


def test_auto_prompted_is_single_batch_call() -> None:
    stub = StubProvider(logprobs=False)
    with Client(provider=stub, fanout="auto") as client:
        response = client.evaluate(
            state="x",
            questions={"a": Noul("A?"), "b": Noul("B?")},
        )
    assert stub.calls == 1
    assert set(response.answers) == {"a", "b"}
    assert response.debug is not None
    assert response.debug.fanout == "batch"
    assert response.debug.requested_fanout == "auto"


def test_auto_measured_is_isolated_calls() -> None:
    stub = StubProvider(logprobs=True)
    with Client(provider=stub, fanout="auto") as client:
        client.evaluate(
            state="x",
            questions={"a": Noul("A?"), "b": Noul("B?")},
        )
    assert stub.calls == 2


def test_isolated_speculative_skips_unmet_gate() -> None:
    stub = StubProvider(logprobs=True)
    with Client(provider=stub, fanout="isolated") as client:
        response = client.evaluate(
            state="x",
            questions={"dept": Choice("Which?", {"billing": "pay", "tech": "bug"})},
            speculative={"sev": Score("severity", ["Low", "High"])},
            when={"sev": {"question": "dept", "equals": "__never__"}},
        )
    assert "dept" in response.answers
    assert "sev" not in response.answers
    assert response.debug is not None
    assert response.debug.skipped_speculative == ["sev"]
    assert stub.calls == 1


def test_isolated_speculative_runs_when_gate_matches() -> None:
    stub = StubProvider(logprobs=True)
    with Client(provider=stub, fanout="isolated") as client:
        first = client.evaluate(
            state="ticket",
            questions={"dept": Choice("Which?", {"billing": "pay", "tech": "bug"})},
        )
    winner = first.answers["dept"].choice
    stub2 = StubProvider(logprobs=True)
    with Client(provider=stub2, fanout="isolated") as client:
        response = client.evaluate(
            state="ticket",
            questions={"dept": Choice("Which?", {"billing": "pay", "tech": "bug"})},
            speculative={"sev": Score("severity", ["Low", "High"])},
            when={"sev": {"question": "dept", "equals": winner}},
        )
    assert "sev" in response.answers
    assert response.debug is not None
    assert response.debug.skipped_speculative == []
    assert stub2.calls == 2


def test_batch_speculative_included_despite_gate() -> None:
    stub = StubProvider(logprobs=False)
    with Client(provider=stub, fanout="batch") as client:
        response = client.evaluate(
            state="x",
            questions={"dept": Choice("Which?", {"billing": "pay", "tech": "bug"})},
            speculative={"sev": Score("severity", ["Low", "High"])},
            when={"sev": {"question": "dept", "equals": "__never__"}},
        )
    assert set(response.answers) == {"dept", "sev"}
    assert stub.calls == 1
    assert response.debug is not None
    assert response.debug.skipped_speculative == []


def test_escalate_reasks_only_uncertain() -> None:
    peaked = {
        "answers": {
            "sure": {
                "type": "choice",
                "choice": "a",
                "probabilities": {"a": 0.99, "b": 0.01},
            },
            "unsure": {
                "type": "choice",
                "choice": "a",
                "probabilities": {"a": 0.4, "b": 0.6},
            },
        }
    }
    isolated_unsure = {
        "answers": {
            "unsure": {
                "type": "choice",
                "choice": "b",
                "probabilities": {"a": 0.1, "b": 0.9},
            }
        }
    }

    class Scripted(StubProvider):
        def complete(self, messages, **kwargs):  # type: ignore[no-untyped-def]
            with self._lock:
                self.calls += 1
            schema = kwargs.get("schema") or {}
            props = schema.get("properties", {}).get("answers", {}).get("properties", {})
            if set(props) == {"sure", "unsure"}:
                return Completion(text=json.dumps(peaked), parsed=peaked, input_tokens=8, output_tokens=8)
            return Completion(
                text=json.dumps(isolated_unsure),
                parsed=isolated_unsure,
                input_tokens=4,
                output_tokens=4,
            )

    stub = Scripted(logprobs=False)
    with Client(provider=stub, fanout="batch") as client:
        response = client.evaluate(
            state="x",
            questions={
                "sure": Choice("Sure?", {"a": None, "b": None}),
                "unsure": Choice("Unsure?", {"a": None, "b": None}),
            },
            escalate="confirm",
        )
    assert stub.calls == 2
    assert response.debug is not None
    assert response.debug.escalated == ["unsure"]
    assert response.answers["unsure"].choice == "b"
    assert "unsure" in response.debug.disagreed


def test_verify_flags_disagreement_without_replacing() -> None:
    first = {
        "answers": {
            "u": {"type": "noul", "noul": 0.2},
        }
    }
    second = {
        "answers": {
            "u": {"type": "noul", "noul": 0.9},
        }
    }

    class Flip(StubProvider):
        def complete(self, messages, **kwargs):  # type: ignore[no-untyped-def]
            with self._lock:
                self.calls += 1
                payload = first if self.calls == 1 else second
            return Completion(text=json.dumps(payload), parsed=payload, input_tokens=3, output_tokens=3)

    stub = Flip(logprobs=False)
    with Client(provider=stub, fanout="batch") as client:
        response = client.evaluate(
            state="x",
            questions={"u": Noul("Y?")},
            verify=True,
        )
    assert response.answers["u"].noul == 0.2
    assert response.debug is not None
    assert response.debug.verified == ["u"]
    assert response.debug.disagreed == ["u"]


def test_cursor_provider_name_sets_second_harness() -> None:
    stub = StubProvider(logprobs=False)
    stub.name = "cursor"
    with Client(provider=stub, fanout="batch") as client:
        response = client.evaluate(state="x", questions={"u": Noul("Y?")})
    assert response.debug is not None
    assert response.debug.second_harness is True


def test_speculative_key_collision_rejected() -> None:
    with Client("stub") as client:
        with pytest.raises(ValidationError):
            client.evaluate(
                state="x",
                questions={"u": Noul("Y?")},
                speculative={"u": Noul("also?")},
            )


@pytest.mark.live
def test_live_ollama_optional() -> None:
    pytest.importorskip("httpx")
    with Client(provider="ollama", model="llama3.1", fanout="isolated") as client:
        try:
            response = client.evaluate(state="hello", questions={"u": Noul("Is this a greeting?")})
        except Exception as exc:
            pytest.skip(f"ollama not reachable: {exc}")
    assert 0 <= response.answers["u"].noul <= 1
