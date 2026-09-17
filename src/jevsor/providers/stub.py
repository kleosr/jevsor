"""Deterministic provider for tests and offline examples. No network."""

from __future__ import annotations

import hashlib
import json
import math
import threading
from typing import Any

from jevsor.providers.base import Completion, TokenAlt


def _stable_unit(text: str) -> float:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64)


def _unit_dist(seed: str, keys: list[str]) -> dict[str, float]:
    masses = [_stable_unit(seed + k) + 0.2 for k in keys]
    total = sum(masses)
    raw = [m / total for m in masses]
    rounded = [round(x, 2) for x in raw]
    rounded[-1] = round(1 - sum(rounded[:-1]), 2)
    return {k: p for k, p in zip(keys, rounded, strict=True)}


class StubProvider:
    name = "stub"

    def __init__(
        self,
        model: str = "stub",
        *,
        scripted: dict[str, Completion] | None = None,
        logprobs: bool = True,
        fail_times: int = 0,
        fail_exc: Exception | None = None,
    ) -> None:
        self.model = model
        self.scripted = scripted or {}
        self._logprobs = logprobs
        self._fail_times = fail_times
        self._fail_exc = fail_exc
        self._lock = threading.Lock()
        self.calls = 0
        self.last_messages: list[dict[str, str]] = []
        self.last_kwargs: dict[str, Any] = {}

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int,
        temperature: float,
        logprobs: bool,
        top_logprobs: int,
        schema: dict[str, Any] | None,
        seed: int | None,
    ) -> Completion:
        with self._lock:
            self.calls += 1
            self.last_messages = messages
            self.last_kwargs = {
                "max_tokens": max_tokens,
                "temperature": temperature,
                "logprobs": logprobs,
                "top_logprobs": top_logprobs,
                "schema": schema,
                "seed": seed,
            }
            if self._fail_times > 0:
                self._fail_times -= 1
                raise self._fail_exc or RuntimeError("stub failure")
        blob = json.dumps(messages, sort_keys=True)
        if blob in self.scripted:
            return self.scripted[blob]
        if schema is not None:
            return self._prompted(messages, schema)
        return self._letter(messages, top_logprobs if logprobs else 0)

    def probe_logprobs(self) -> bool:
        return self._logprobs

    def close(self) -> None:
        return None

    def _letter(self, messages: list[dict[str, str]], top_k: int) -> Completion:
        prompt = messages[-1]["content"]
        # Prefer letters declared in the prompt ("A = ...") so tests stay stable.
        declared = [
            line[0]
            for line in prompt.splitlines()
            if len(line) >= 3 and line[1:3] == " =" and (line[0].isalpha() or line[0].isdigit())
        ]
        letters = declared or ["Y", "N"]
        weights = []
        for letter in letters:
            weights.append(0.15 + _stable_unit(prompt + letter))
        z = sum(math.exp(w) for w in weights)
        probs = [math.exp(w) / z for w in weights]
        winner_i = max(range(len(letters)), key=lambda i: probs[i])
        winner = letters[winner_i]
        alts = [
            TokenAlt(token=letters[i], logprob=math.log(max(probs[i], 1e-12)))
            for i in range(len(letters))
        ]
        alts.sort(key=lambda a: a.logprob, reverse=True)
        if top_k:
            alts = alts[:top_k]
        return Completion(
            text=winner,
            token_alts=[alts],
            input_tokens=max(1, len(prompt) // 4),
            output_tokens=1,
        )

    def _prompted(self, messages: list[dict[str, str]], schema: dict[str, Any]) -> Completion:
        prompt = messages[-1]["content"]
        answers: dict[str, Any] = {}
        props = (
            schema.get("properties", {})
            .get("answers", {})
            .get("properties", {})
        )
        if not props:
            # Single-question schema
            answers = self._one_prompted(prompt, schema)
            payload = answers
        else:
            for qid, qschema in props.items():
                answers[qid] = self._one_prompted(prompt + qid, qschema)
            payload = {"answers": answers}
        text = json.dumps(payload)
        return Completion(
            text=text,
            parsed=payload,
            input_tokens=max(1, len(prompt) // 4),
            output_tokens=max(1, len(text) // 4),
        )

    def _one_prompted(self, seed: str, schema: dict[str, Any]) -> dict[str, Any]:
        qtype = schema.get("properties", {}).get("type", {}).get("const")
        if qtype == "choice" or "choice" in schema.get("required", []):
            options = list(
                schema.get("properties", {}).get("probabilities", {}).get("required", ["a", "b"])
            )
            if len(options) < 2:
                options = ["a", "b"]
            probs = _unit_dist(seed, options)
            choice = max(probs, key=lambda k: probs[k])
            return {"type": "choice", "choice": choice, "probabilities": probs}
        if qtype == "score" or "score" in schema.get("required", []):
            levels = list(
                schema.get("properties", {}).get("probabilities", {}).get("required", ["low", "high"])
            )
            probs = _unit_dist(seed, levels)
            score = round(sum(i * probs[level] for i, level in enumerate(levels)), 2)
            return {"type": "score", "score": score, "probabilities": probs}
        p = round(0.15 + 0.7 * _stable_unit(seed + "noul"), 2)
        return {"type": "noul", "noul": p}
