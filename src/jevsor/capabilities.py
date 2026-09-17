"""Static defaults plus runtime logprobs probe cache. Probe wins over the matrix."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Tier = Literal["measured", "prompted", "unknown"]

# Defaults only. Gemini 3.x withdrew logprobs; Ollama Cloud drops the fields.
# First-use probe overwrites this per (provider, model).
DEFAULT_TIER: dict[str, Tier] = {
    "stub": "measured",
    "ollama": "measured",
    "openai": "measured",
    "openai_compat": "measured",
    "llamacpp": "measured",
    "gemini": "unknown",
    "anthropic": "prompted",
    "cursor": "prompted",
}

TOP_LOGPROBS = 20
WIDE_CHOICE = 20
PROBE_CACHE: dict[tuple[str, str], bool] = {}


@dataclass(frozen=True)
class Capability:
    logprobs: bool
    top_k: int = TOP_LOGPROBS
    seed: bool = False
    structured: bool = False


def default_logprobs(provider: str) -> bool | None:
    tier = DEFAULT_TIER.get(provider, "unknown")
    if tier == "measured":
        return True
    if tier == "prompted":
        return False
    return None


def cache_key(provider: str, model: str) -> tuple[str, str]:
    return (provider, model)


def remembered(provider: str, model: str) -> bool | None:
    return PROBE_CACHE.get(cache_key(provider, model))


def remember(provider: str, model: str, supported: bool) -> None:
    PROBE_CACHE[cache_key(provider, model)] = supported


def clear_probe_cache() -> None:
    PROBE_CACHE.clear()
