"""Provider protocol. Implementations talk HTTP; the runner owns codecs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from jevsor.letter import TokenAlt as LetterTokenAlt


@dataclass(frozen=True)
class TokenAlt:
    token: str
    logprob: float

    def as_letter(self) -> LetterTokenAlt:
        return LetterTokenAlt(token=self.token, logprob=self.logprob)


@dataclass
class Completion:
    text: str
    token_alts: list[list[TokenAlt]] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    refusal: str | None = None
    parsed: dict[str, Any] | None = None


class Provider(Protocol):
    name: str
    model: str

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
    ) -> Completion: ...

    def close(self) -> None: ...
