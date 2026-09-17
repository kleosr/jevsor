"""Anthropic Messages API. No logprobs by vendor design — prompted JSON only."""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

from jevsor.errors import AuthError, OverloadedError, ProviderError, RateLimitError
from jevsor.providers.base import Completion

DEFAULT_ANTHROPIC = "https://api.anthropic.com/v1"
API_VERSION = "2023-06-01"


class AnthropicPromptedProvider:
    name = "anthropic"

    def __init__(
        self,
        model: str = "claude-sonnet-4-5",
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.model = model
        self.api_key = api_key if api_key is not None else os.environ.get("ANTHROPIC_API_KEY", "")
        self.base_url = (base_url or DEFAULT_ANTHROPIC).rstrip("/")
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
        del logprobs, top_logprobs, seed
        if not self.api_key:
            raise AuthError("ANTHROPIC_API_KEY is missing")
        system = ""
        filtered: list[dict[str, str]] = []
        for message in messages:
            if message["role"] == "system":
                system += message["content"] + "\n"
            else:
                filtered.append(message)
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max(max_tokens, 32),
            "temperature": temperature,
            "messages": filtered,
        }
        if system.strip():
            body["system"] = system.strip()
        headers = {
            "content-type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": API_VERSION,
        }
        response = self._client.post(f"{self.base_url}/messages", json=body, headers=headers)
        if response.status_code == 401:
            raise AuthError(response.text)
        if response.status_code == 429:
            retry = response.headers.get("retry-after")
            wait = float(retry) if retry else None
            raise RateLimitError(response.text, retry_after=wait)
        if response.status_code == 529:
            raise OverloadedError(response.text)
        if response.status_code >= 400:
            raise ProviderError(response.text, status=response.status_code)
        data = response.json()
        text = "".join(
            block.get("text", "")
            for block in data.get("content") or []
            if block.get("type") == "text"
        )
        usage = data.get("usage") or {}
        parsed = None
        if text:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                start = text.find("{")
                end = text.rfind("}")
                if start >= 0 and end > start:
                    parsed = json.loads(text[start : end + 1])
        return Completion(
            text=text,
            parsed=parsed,
            input_tokens=int(usage.get("input_tokens") or 0),
            output_tokens=int(usage.get("output_tokens") or 0),
        )

    def probe_logprobs(self) -> bool:
        return False

    def close(self) -> None:
        self._client.close()
