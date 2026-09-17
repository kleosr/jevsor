"""Client: validate → probe → batch or isolated fan-out → normalize."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Literal

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from jevsor.version import __version__
from jevsor.capabilities import WIDE_CHOICE, default_logprobs, remember, remembered
from jevsor.codecs import extract_answers_blob, measured_answer, prompted_answer
from jevsor.contract import (
    Answer,
    ChoiceQuestion,
    Debug,
    EvaluateRequest,
    Noul,
    NoulAnswer,
    Question,
    QuestionDebug,
    Response,
    Usage,
)
from jevsor.letter import letter_ok
from jevsor.prompts import letter_prompt, prompted_prompt, prompted_schema
from jevsor.providers import Completion, Provider, build_provider
from jevsor.validate import parse_request, round2, validate_distribution
from jevsor.confidence import confidence_from_distribution
from jevsor.contract import ChoiceAnswer
from jevsor.errors import JevsorError, ProviderError, RateLimitError, ValidationError

Fanout = Literal["batch", "isolated"]
TRANSPORT_ATTEMPTS = 3
CORRECTIVE_ATTEMPTS = 2
DEFAULT_CONCURRENCY = 8


class Client:
    def __init__(
        self,
        provider: str | Provider = "stub",
        model: str = "stub",
        *,
        fanout: Fanout = "batch",
        temperature: float = 0.0,
        seed: int | None = 0,
        concurrency: int = DEFAULT_CONCURRENCY,
        partial: bool = False,
        **provider_kwargs: Any,
    ) -> None:
        if isinstance(provider, str):
            self._owns = True
            self.provider = build_provider(provider, model, **provider_kwargs)
        else:
            self._owns = False
            self.provider = provider
        self.fanout = fanout
        self.temperature = temperature
        self.seed = seed
        self.concurrency = concurrency
        self.partial = partial

    def close(self) -> None:
        if self._owns:
            self.provider.close()

    def __enter__(self) -> Client:
        return self
    def __exit__(self, *exc: object) -> None:
        self.close()

    def evaluate(
        self,
        state: Any = None,
        questions: dict[str, Question] | None = None,
        *,
        fanout: Fanout | None = None,
        **payload: Any,
    ) -> Response:
        if questions is not None:
            body: Any = {"state": state, "questions": questions, **payload}
        elif isinstance(state, dict) and "questions" in state:
            body = {**state, **payload}
        elif payload:
            body = payload
        else:
            raise ValidationError("questions are required")
        req = parse_request(body)
        mode = fanout or self.fanout
        measured = self._logprobs_ok()
        if mode == "isolated":
            return self._isolated(req, measured)
        return self._batch(req, measured)

    async def aevaluate(self, *args: Any, **kwargs: Any) -> Response:
        import asyncio

        return await asyncio.to_thread(self.evaluate, *args, **kwargs)

    def _logprobs_ok(self) -> bool:
        probe = getattr(self.provider, "probe_logprobs", None)
        cached = remembered(self.provider.name, self.provider.model)
        if cached is not None:
            return cached
        if callable(probe):
            try:
                supported = bool(probe())
            except JevsorError:
                supported = False
            remember(self.provider.name, self.provider.model, supported)
            return supported
        fallback = default_logprobs(self.provider.name)
        return bool(fallback)

    def _complete(self, **kwargs: Any) -> Completion:
        @retry(
            reraise=True,
            stop=stop_after_attempt(TRANSPORT_ATTEMPTS),
            wait=wait_exponential_jitter(initial=0.2, max=2),
            retry=retry_if_exception_type((RateLimitError, ProviderError)),
        )
        def call() -> Completion:
            return self.provider.complete(
                kwargs["messages"],
                max_tokens=kwargs["max_tokens"],
                temperature=self.temperature,
                logprobs=kwargs.get("logprobs", False),
                top_logprobs=kwargs.get("top_logprobs", 20),
                schema=kwargs.get("schema"),
                seed=self.seed,
            )
        return call()

    def _batch(self, req: EvaluateRequest, measured: bool) -> Response:
        if measured and all(letter_ok(q, WIDE_CHOICE) for q in req.questions.values()):
            return self._isolated(req, True)
        return self._prompted_all(req)

    def _prompted_all(self, req: EvaluateRequest) -> Response:
        schema = prompted_schema(req.questions)
        messages = [
            {"role": "system", "content": "Return only JSON."},
            {"role": "user", "content": prompted_prompt(req.state, req.questions)},
        ]
        parsed = None
        usage = Usage()
        last_err: Exception | None = None
        for attempt in range(1, CORRECTIVE_ATTEMPTS + 1):
            completion = self._complete(
                messages=messages,
                max_tokens=512,
                logprobs=False,
                schema=schema,
            )
            usage = usage.plus(Usage(input_tokens=completion.input_tokens, output_tokens=completion.output_tokens))
            try:
                parsed = completion.parsed or json.loads(completion.text)
                blob = extract_answers_blob(parsed, req.questions)
                answers = {
                    qid: prompted_answer(q, blob[qid])
                    for qid, q in req.questions.items()
                }
                return self._response(req, answers, usage, "prompted", attempt, "batch")
            except (KeyError, json.JSONDecodeError, ValidationError, TypeError) as exc:
                last_err = exc
                messages.append({"role": "assistant", "content": completion.text})
                messages.append({"role": "user", "content": f"Repair JSON: {exc}. Return only JSON."})
        raise ValidationError(
            f"prompted output failed after retries: {last_err}; last={completion.text[:400]!r}"
        )

    def _isolated(self, req: EvaluateRequest, measured: bool) -> Response:
        answers: dict[str, Answer] = {}
        usage = Usage()
        debug_q: dict[str, QuestionDebug] = {}
        items = list(req.questions.items())

        def one(qid: str, question: Question) -> tuple[str, Answer, Usage, QuestionDebug]:
            if measured and isinstance(question, ChoiceQuestion) and len(question.criteria) > WIDE_CHOICE:
                return qid, *self._wide_choice(req.state, question)
            if measured and letter_ok(question, WIDE_CHOICE):
                return qid, *self._measured_one(req.state, question)
            return qid, *self._prompted_one(req.state, qid, question)

        if self.partial:
            raise ValidationError("partial isolated mode is not in v0.1; all-or-nothing only")
        workers = min(self.concurrency, len(items)) or 1
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(one, qid, q) for qid, q in items]
            try:
                for fut in as_completed(futures):
                    qid, answer, used, qdebug = fut.result()
                    answers[qid] = answer
                    usage = usage.plus(used)
                    debug_q[qid] = qdebug
            except Exception:
                for fut in futures:
                    fut.cancel()
                raise
        ordered = {qid: answers[qid] for qid in req.questions}
        return self._response(req, ordered, usage, None, 1, "isolated", debug_q)

    def _measured_one(self, state: Any, question: Question) -> tuple[Answer, Usage, QuestionDebug]:
        prompt, mapping = letter_prompt(state, question)
        completion = self._complete(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1,
            logprobs=True,
            top_logprobs=20,
            schema=None,
        )
        answer = measured_answer(question, completion, mapping)
        used = Usage(input_tokens=completion.input_tokens, output_tokens=completion.output_tokens)
        debug = QuestionDebug(mode="letter", provenance="measured", truncated=getattr(answer, "truncated", False), temperature=self.temperature, seed=self.seed)
        return answer, used, debug

    def _prompted_one(self, state: Any, qid: str, question: Question) -> tuple[Answer, Usage, QuestionDebug]:
        subset = {qid: question}
        schema = prompted_schema(subset)
        completion = self._complete(
            messages=[{"role": "user", "content": prompted_prompt(state, subset)}],
            max_tokens=256,
            logprobs=False,
            schema=schema,
        )
        blob = extract_answers_blob(completion.parsed or json.loads(completion.text), subset)
        payload = blob.get(qid, blob)
        answer = prompted_answer(question, payload)
        used = Usage(input_tokens=completion.input_tokens, output_tokens=completion.output_tokens)
        debug = QuestionDebug(mode="prompted", provenance="prompted", temperature=self.temperature, seed=self.seed)
        return answer, used, debug

    def _wide_choice(self, state: Any, question: ChoiceQuestion) -> tuple[Answer, Usage, QuestionDebug]:
        usage = Usage()
        masses: dict[str, float] = {}
        for key, desc in question.criteria.items():
            extra = f" {desc}" if desc else ""
            noul_q = Noul(f"Does this state match option {key}?{extra}")
            answer, used, _ = self._measured_one(state, noul_q)
            usage = usage.plus(used)
            masses[key] = float(answer.noul) if isinstance(answer, NoulAnswer) else 0.0
        total = sum(masses.values())
        if total <= 0:
            probs = {k: round2(1 / len(masses)) for k in masses}
        else:
            probs = {k: round2(v / total) for k, v in masses.items()}
        probs = validate_distribution(probs, expected_keys=list(question.criteria))
        choice = max(probs, key=lambda k: probs[k])
        result = ChoiceAnswer(
            choice=choice,
            probabilities=probs,
            confidence=confidence_from_distribution(probs),
            provenance="measured",
            truncated=True,
            missing_mass=0.0,
        )
        debug = QuestionDebug(mode="wide-choice", provenance="measured", truncated=True, temperature=self.temperature, seed=self.seed)
        return result, usage, debug

    def _response(
        self,
        req: EvaluateRequest,
        answers: dict[str, Answer],
        usage: Usage,
        default_mode: str | None,
        attempts: int,
        fanout: Fanout,
        debug_q: dict[str, QuestionDebug] | None = None,
    ) -> Response:
        provenances = {a.provenance for a in answers.values()}
        mixed = len(provenances) > 1
        if debug_q is None:
            debug_q = {
                qid: QuestionDebug(
                    mode=default_mode or "prompted",
                    provenance=ans.provenance,
                    attempts=attempts,
                    temperature=self.temperature,
                    seed=self.seed,
                )
                for qid, ans in answers.items()
            }
        debug = Debug(
            provider=self.provider.name,
            model=self.provider.model,
            jevsor_version=__version__,
            fanout=fanout,
            mixed_provenance=mixed,
            questions=debug_q,
        )
        return Response(
            model=self.provider.model,
            answers=answers,
            usage=usage,
            mixed_provenance=mixed,
            debug=debug,
        )

