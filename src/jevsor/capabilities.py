"""Capability matrix plus a process-local logprobs probe cache.

This cache is NOT an answer cache. It remembers whether a backend returned
top_logprobs on a 1-token probe.

Scope: the **MCP server process** (the stdio child Cursor spawned), not the
Cursor chat session. A session restart usually respawns MCP and clears it.
A long-lived MCP process reuses the boolean across chat turns — that is
intended; the value is a capability bit, not a decision.

Key: SHA-256 prefix of (provider, model, endpoint). The model string must
include any version or variant the catalog exposes (`grok-4.6` vs
`grok-4.6:high`). If a host silently swaps weights behind the same id, the
cache can go stale — pin versioned ids when the catalog offers them.

Invalidation: `clear_probe_cache()`, process exit, or a different endpoint.
It never keys on state, questions, or embeddings.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

Tier = Literal["measured", "prompted", "unknown"]

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
PROBE_CACHE: dict[str, bool] = {}


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


def endpoint_of(provider: object) -> str:
    return str(getattr(provider, "base_url", "") or "")


def cache_key(provider: str, model: str, endpoint: str = "") -> str:
    raw = f"{provider}\0{model}\0{endpoint}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def remembered(provider: str, model: str, endpoint: str = "") -> bool | None:
    return PROBE_CACHE.get(cache_key(provider, model, endpoint))


def remember(provider: str, model: str, supported: bool, endpoint: str = "") -> None:
    PROBE_CACHE[cache_key(provider, model, endpoint)] = supported


def clear_probe_cache() -> None:
    PROBE_CACHE.clear()
