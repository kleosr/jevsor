"""OpenAI-compatible chat completions (OpenAI, llama.cpp, LM Studio, Ollama /v1)."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from jevsor.errors import AuthError, OverloadedError, ProviderError, RateLimitError, RefusalError
from jevsor.providers.base import Completion, TokenAlt

DEFAULT_OPENAI = "https://api.openai.com/v1"


def _map_status(status: int, body: str, headers: httpx.Headers) -> Exception:
    if status == 401:
        return AuthError(body or "unauthorized")
    if status == 429:
        retry = headers.get("retry-after")
        wait = float(retry) if retry else None
        return RateLimitError(body or "rate limited", retry_after=wait)
    if status == 529:
        return OverloadedError(body or "overloaded")
    if status in {500, 502, 503, 504}:
        return ProviderError(body or f"provider {status}", status=status)
    return ProviderError(body or f"provider {status}", status=status)


class OpenAICompatProvider:
    name = "openai_compat"

    def __init__(
        self,
        model: str,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 60.0,
        name: str | None = None,
    ) -> None:
        self.model = model
        if name:
            self.name = name
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL") or DEFAULT_OPENAI).rstrip("/")
        self.api_key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")
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
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if logprobs:
            payload["logprobs"] = True
            payload["top_logprobs"] = top_logprobs
        if seed is not None:
            payload["seed"] = seed
        if schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "jevsor", "schema": schema, "strict": True},
            }
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        response = self._client.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            headers=headers,
        )
        if response.status_code >= 400:
            raise _map_status(response.status_code, response.text, response.headers)
        data = response.json()
        return _parse_openai(data)

    def probe_logprobs(self) -> bool:
        probe = self.complete(
            [{"role": "user", "content": "Reply with X"}],
            max_tokens=1,
            temperature=0,
            logprobs=True,
            top_logprobs=1,
            schema=None,
            seed=0,
        )
        return bool(probe.token_alts)

    def close(self) -> None:
        self._client.close()


def _parse_openai(data: dict[str, Any]) -> Completion:
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    refusal = message.get("refusal")
    if refusal:
        raise RefusalError(str(refusal))
    text = message.get("content") or ""
    usage = data.get("usage") or {}
    alts: list[list[TokenAlt]] = []
    content = (choice.get("logprobs") or {}).get("content") or []
    for token in content:
        tops = [
            TokenAlt(token=item.get("token", ""), logprob=float(item.get("logprob", 0)))
            for item in token.get("top_logprobs") or []
        ]
        if not tops and token.get("token"):
            tops = [TokenAlt(token=token.get("token", ""), logprob=float(token.get("logprob", 0)))]
        alts.append(tops)
    parsed = None
    if text:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
    return Completion(
        text=text,
        token_alts=alts,
        input_tokens=int(usage.get("prompt_tokens") or 0),
        output_tokens=int(usage.get("completion_tokens") or 0),
        parsed=parsed,
    )
