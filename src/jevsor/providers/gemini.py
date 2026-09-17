"""Gemini generateContent. Logprobs are probed; 3.x may have withdrawn them."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from jevsor.errors import AuthError, ProviderError, RateLimitError
from jevsor.providers.base import Completion, TokenAlt

DEFAULT_GEMINI = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider:
    name = "gemini"

    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.model = model
        self.api_key = api_key if api_key is not None else os.environ.get("GEMINI_API_KEY", "")
        self.base_url = (base_url or DEFAULT_GEMINI).rstrip("/")
        self._client = httpx.Client(timeout=timeout)

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
        if not self.api_key:
            raise AuthError("GEMINI_API_KEY is missing")
        contents = [{"role": "user" if m["role"] != "assistant" else "model", "parts": [{"text": m["content"]}]} for m in messages]
        generation: dict[str, Any] = {
            "maxOutputTokens": max_tokens,
            "temperature": temperature,
        }
        if logprobs:
            generation["responseLogprobs"] = True
            generation["logprobs"] = top_logprobs
        body: dict[str, Any] = {"contents": contents, "generationConfig": generation}
        if schema is not None:
            generation["responseMimeType"] = "application/json"
            generation["responseJsonSchema"] = schema
        url = f"{self.base_url}/models/{self.model}:generateContent"
        response = self._client.post(url, params={"key": self.api_key}, json=body)
        if response.status_code == 401:
            raise AuthError(response.text)
        if response.status_code == 429:
            raise RateLimitError(response.text)
        if response.status_code >= 400:
            raise ProviderError(response.text, status=response.status_code)
        data = response.json()
        return _parse_gemini(data)

    def probe_logprobs(self) -> bool:
        try:
            probe = self.complete(
                [{"role": "user", "content": "Reply with X"}],
                max_tokens=1,
                temperature=0,
                logprobs=True,
                top_logprobs=1,
                schema=None,
                seed=None,
            )
        except ProviderError:
            return False
        return bool(probe.token_alts)

    def close(self) -> None:
        self._client.close()


def _parse_gemini(data: dict[str, Any]) -> Completion:
    cand = (data.get("candidates") or [{}])[0]
    parts = ((cand.get("content") or {}).get("parts") or [{}])
    text = "".join(part.get("text", "") for part in parts)
    alts: list[list[TokenAlt]] = []
    logprobs = cand.get("logprobsResult") or {}
    for step in logprobs.get("topCandidates") or []:
        row = [
            TokenAlt(
                token=(item.get("token") or ""),
                logprob=float(item.get("logProbability") or 0),
            )
            for item in step.get("candidates") or []
        ]
        if row:
            alts.append(row)
    usage = data.get("usageMetadata") or {}
    parsed = None
    if text:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
    return Completion(
        text=text,
        token_alts=alts,
        input_tokens=int(usage.get("promptTokenCount") or 0),
        output_tokens=int(usage.get("candidatesTokenCount") or 0),
        parsed=parsed,
    )
