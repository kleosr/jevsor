from typing import Any

from jevsor.errors import ValidationError
from jevsor.providers.anthropic_prompted import AnthropicPromptedProvider
from jevsor.providers.base import Completion, Provider, TokenAlt
from jevsor.providers.gemini import GeminiProvider
from jevsor.providers.ollama import OllamaProvider
from jevsor.providers.openai_compat import OpenAICompatProvider
from jevsor.providers.stub import StubProvider

__all__ = [
    "AnthropicPromptedProvider",
    "Completion",
    "GeminiProvider",
    "OllamaProvider",
    "OpenAICompatProvider",
    "Provider",
    "StubProvider",
    "TokenAlt",
    "build_provider",
]


def build_provider(kind: str, model: str, **kwargs: Any) -> Provider:
    if kind == "stub":
        return StubProvider(model=model, **kwargs)
    if kind == "ollama":
        return OllamaProvider(model=model, **kwargs)
    if kind in {"openai", "openai_compat", "llamacpp"}:
        name = "llamacpp" if kind == "llamacpp" else "openai_compat"
        return OpenAICompatProvider(model=model, name=name, **kwargs)
    if kind == "gemini":
        return GeminiProvider(model=model, **kwargs)
    if kind == "anthropic":
        return AnthropicPromptedProvider(model=model, **kwargs)
    if kind == "cursor":
        from jevsor.providers.cursor_agent import CursorAgentProvider

        return CursorAgentProvider(model=model, **kwargs)
    raise ValidationError(f"unknown provider {kind!r}")

