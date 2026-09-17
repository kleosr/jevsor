"""Ollama local server via its OpenAI-compatible /v1 endpoint."""

from __future__ import annotations

import os

from jevsor.providers.openai_compat import OpenAICompatProvider

DEFAULT_OLLAMA = "http://127.0.0.1:11434/v1"


class OllamaProvider(OpenAICompatProvider):
    name = "ollama"

    def __init__(
        self,
        model: str = "llama3.1",
        *,
        base_url: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        url = base_url or os.environ.get("OLLAMA_BASE_URL") or DEFAULT_OLLAMA
        super().__init__(
            model=model,
            base_url=url,
            api_key=os.environ.get("OLLAMA_API_KEY", "ollama"),
            timeout=timeout,
            name="ollama",
        )
