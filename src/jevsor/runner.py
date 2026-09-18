"""Client: validate → probe → batch or isolated fan-out → optional escalate/verify."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Literal

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from jevsor.version import __version__
from jevsor.capabilities import WIDE_CHOICE, default_logprobs, endpoint_of, remember, remembered
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
from jevsor.calibrate import rescale_answer
from jevsor.letter import letter_ok
from jevsor.policy import (
    EscalateMode,
    Gate,
    answers_disagree,
    parse_gate,
    select_escalation,
    select_speculative,
)
from jevsor.prompts import letter_prompt, prompted_prompt, prompted_schema
from jevsor.providers import Completion, Provider, build_provider
from jevsor.schedule import RequestedFanout, resolve_fanout
from jevsor.validate import parse_request, round2, validate_distribution
from jevsor.confidence import confidence_from_distribution
from jevsor.contract import ChoiceAnswer
from jevsor.errors import JevsorError, ProviderError, RateLimitError, ValidationError

Fanout = RequestedFanout
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
        scale_temperature: float | None = None,
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
        self.scale_temperature = scale_temperature

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
        speculative: dict[str, Any] | None = None,
        when: dict[str, Any] | None = None,
        escalate: EscalateMode | list[str] = False,
        verify: bool | list[str] = False,
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
        spec_from_body = body.pop("speculative", None) if isinstance(body, dict) else None
        when_from_body = body.pop("when", None) if isinstance(body, dict) else None
        escalate_from_body = body.pop("escalate", None) if isinstance(body, dict) else None
        verify_from_body = body.pop("verify", None) if isinstance(body, dict) else None
        req = parse_request(body)
        spec_map, gates = _parse_speculative(
            speculative if speculative is not None else spec_from_body,
            when if when is not None else when_from_body,
        )
        overlap = set(req.questions) & set(spec_map)
        if overlap:
            raise ValidationError(f"speculative ids collide with questions: {sorted(overlap)}")
        requested = fanout or self.fanout
        measured = self._logprobs_ok()
        mode = resolve_fanout(requested, measured=measured, questions=req.questions)
        if escalate_from_body is not None and escalate is False:
            escalate = escalate_from_body
        if verify_from_body is not None and verify is False:
            verify = verify_from_body
        return self._decide(
            req,
            spec_map,
            gates,
            measured=measured,
            mode=mode,
            requested=requested,
            escalate=escalate,
            verify=verify,
        )

    async def aevaluate(self, *args: Any, **kwargs: Any) -> Response:
        import asyncio

        return await asyncio.to_thread(self.evaluate, *args, **kwargs)

    def _logprobs_ok(self) -> bool:
        probe = getattr(self.provider, "probe_logprobs", None)
        cached = remembered(self.provider.name, self.provider.model, endpoint_of(self.provider))
        if cached is not None:
            return cached
        if callable(probe):
            try:
                supported = bool(probe())
            except JevsorError:
                supported = False
            remember(self.provider.name, self.provider.model, supported, endpoint_of(self.provider))
            return supported
        fallback = default_logprobs(self.provider.name)
        return bool(fallback)

    def _decide(
        self,
        req: EvaluateRequest,
        speculative: dict[str, Question],
        gates: dict[str, Gate],
        *,
        measured: bool,
        mode: Literal["batch", "isolated"],
        requested: Fanout,
        escalate: EscalateMode | list[str],
        verify: bool | list[str],
    ) -> Response:
        skipped: list[str] = []
        catalog = {**req.questions, **speculative}
        if mode == "batch":
            merged = EvaluateRequest(
                state=req.state,
                questions={**req.questions, **speculative},
                model=req.model,
            )
            primary = self._prompted_all(merged)
        else:
            primary = self._isolated(req, measured)
            if speculative:
                run_ids, skipped = select_speculative(speculative, gates, primary.answers)
                if run_ids:
                    extra_req = EvaluateRequest(
                        state=req.state,
                        questions={qid: speculative[qid] for qid in run_ids},
                        model=req.model,
                    )
                    extra = self._isolated(extra_req, measured)
                    primary = self._absorb(req, primary, extra, measured)
        escalated: list[str] = []
        disagreed: list[str] = []
        verified: list[str] = []
        if escalate:
            ids = select_escalation(primary.answers, escalate)
            questions = {qid: catalog[qid] for qid in ids if qid in catalog}
            if questions:
                second = self._isolated(
                    EvaluateRequest(state=req.state, questions=questions, model=req.model),
                    measured,
                )
                for qid, answer in second.answers.items():
                    if qid in primary.answers and answers_disagree(primary.answers[qid], answer):
                        disagreed.append(qid)
                primary = self._absorb(req, primary, second, measured, replace=True)
                escalated = list(questions)
        if verify:
            verify_ids = (
                [qid for qid in verify if qid in primary.answers]
                if isinstance(verify, list)
                else list(primary.answers)
            )
            questions = {qid: catalog[qid] for qid in verify_ids if qid in catalog}
            if questions:
                third = self._isolated(
                    EvaluateRequest(state=req.state, questions=questions, model=req.model),
                    measured,
                )
                for qid, answer in third.answers.items():
                    if qid in primary.answers and answers_disagree(primary.answers[qid], answer):
                        if qid not in disagreed:
                            disagreed.append(qid)
                primary = self._absorb(req, primary, third, measured, replace=False)
                verified = list(questions)
        return self._with_schedule(
            primary,
            requested=requested,
            skipped=skipped,
            escalated=escalated,
            disagreed=disagreed,
            verified=verified,
            measured=measured,
        )

    def _absorb(
        self,
        req: EvaluateRequest,
        base: Response,
        extra: Response,
        measured: bool,
        *,
        replace: bool = True,
    ) -> Response:
        answers = dict(base.answers)
        if replace:
            answers.update(extra.answers)
        usage = base.usage.plus(extra.usage)
        debug_q = {}
        if base.debug:
            debug_q.update(base.debug.questions)
        if extra.debug and replace:
            debug_q.update(extra.debug.questions)
        fanout: Literal["batch", "isolated"] = (
            base.debug.fanout if base.debug else ("isolated" if measured else "batch")
        )
        return self._response(req, answers, usage, None, 1, fanout, debug_q)

    def _with_schedule(
        self,
        response: Response,
        *,
        requested: Fanout,
        skipped: list[str],
        escalated: list[str],
        disagreed: list[str],
        verified: list[str],
        measured: bool,
    ) -> Response:
        if response.debug is None:
            return response
        response.debug.requested_fanout = requested
        response.debug.second_harness = self.provider.name == "cursor"
        response.debug.skipped_speculative = skipped
        response.debug.escalated = escalated
        response.debug.disagreed = disagreed
        response.debug.verified = verified
        response.debug.measured = measured
        return response

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
        answer = rescale_answer(measured_answer(question, completion, mapping), self.scale_temperature)
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
        result = rescale_answer(result, self.scale_temperature)
        debug = QuestionDebug(mode="wide-choice", provenance="measured", truncated=True, temperature=self.temperature, seed=self.seed)
        return result, usage, debug

    def _response(
        self,
        req: EvaluateRequest,
        answers: dict[str, Answer],
        usage: Usage,
        default_mode: str | None,
        attempts: int,
        fanout: Literal["batch", "isolated"],
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


def _parse_speculative(
    speculative: Any,
    when: Any,
) -> tuple[dict[str, Question], dict[str, Gate]]:
    if not speculative:
        return {}, {}
    if not isinstance(speculative, dict):
        raise ValidationError("speculative must be an object")
    gates: dict[str, Gate] = {}
    if when:
        if not isinstance(when, dict):
            raise ValidationError("when must be an object")
        for qid, raw in when.items():
            try:
                gates[str(qid)] = parse_gate(raw)
            except ValueError as exc:
                raise ValidationError(str(exc)) from exc
    cleaned: dict[str, Any] = {}
    for qid, item in speculative.items():
        payload = item
        if isinstance(item, dict) and "when" in item:
            payload = {key: value for key, value in item.items() if key != "when"}
            if qid not in gates:
                try:
                    gates[str(qid)] = parse_gate(item.get("when"))
                except ValueError as exc:
                    raise ValidationError(str(exc)) from exc
        cleaned[str(qid)] = payload
    parsed = parse_request({"state": None, "questions": cleaned})
    return parsed.questions, gates


