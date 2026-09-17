"""MCP stdio server. Tools: evaluate, route. stdout is JSON-RPC only."""

from __future__ import annotations

import os
from typing import Any

from jevsor.contract import Question
from jevsor.errors import JevsorError, ValidationError
from jevsor.policy import route_answers
from jevsor.runner import Client, Fanout
from jevsor.validate import parse_request


def _fanout(raw: str | None) -> Fanout:
    if raw == "isolated":
        return "isolated"
    if raw == "auto":
        return "auto"
    return "batch"


def _escalate(raw: Any) -> Any:
    if raw in (None, False, "false", "0", ""):
        return False
    if raw in (True, "true", "1"):
        return True
    if raw in ("confirm", "human"):
        return raw
    if isinstance(raw, list):
        return [str(item) for item in raw]
    raise ValidationError(f"unsupported escalate value {raw!r}")


def _verify(raw: Any) -> bool | list[str]:
    if raw in (None, False, "false", "0", ""):
        return False
    if raw in (True, "true", "1"):
        return True
    if isinstance(raw, list):
        return [str(item) for item in raw]
    raise ValidationError(f"unsupported verify value {raw!r}")


def evaluate_payload(
    state: Any,
    questions: dict[str, Any],
    *,
    provider: str | None = None,
    model: str | None = None,
    fanout: Fanout = "batch",
    speculative: dict[str, Any] | None = None,
    when: dict[str, Any] | None = None,
    escalate: Any = False,
    verify: Any = False,
) -> dict[str, Any]:
    kind = provider or os.environ.get("JEVSOR_PROVIDER", "stub")
    name = model or os.environ.get("JEVSOR_MODEL", "stub")
    req = parse_request({"state": state, "questions": questions})
    parsed: dict[str, Question] = req.questions
    with Client(provider=kind, model=name, fanout=fanout) as client:
        response = client.evaluate(
            state=req.state,
            questions=parsed,
            speculative=speculative,
            when=when,
            escalate=_escalate(escalate),
            verify=_verify(verify),
        )
    return response.model_dump()


def create_server() -> Any:
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("jevsor")

    @server.tool()
    def evaluate(
        questions: dict[str, Any],
        state: Any = None,
        provider: str | None = None,
        model: str | None = None,
        fanout: str = "batch",
        speculative: dict[str, Any] | None = None,
        when: dict[str, Any] | None = None,
        escalate: Any = False,
        verify: Any = False,
    ) -> dict[str, Any]:
        """Typed Choice/Score/Noul decisions over gathered state. Not a second agent loop."""
        try:
            return evaluate_payload(
                state,
                questions,
                provider=provider,
                model=model,
                fanout=_fanout(fanout),
                speculative=speculative,
                when=when,
                escalate=escalate,
                verify=verify,
            )
        except JevsorError as exc:
            return {"error": str(exc), "status": exc.status}

    @server.tool()
    def route(
        answers: dict[str, Any],
        low: float = 0.5,
        high: float = 0.8,
    ) -> dict[str, Any]:
        """Map evaluate answers onto act/confirm/human bands. Thresholds stay in code."""
        try:
            return {"routes": route_answers(answers, low=low, high=high)}
        except (JevsorError, ValueError) as exc:
            status = getattr(exc, "status", 422)
            return {"error": str(exc), "status": status}

    return server


def main() -> None:
    try:
        server = create_server()
    except ImportError as exc:
        raise SystemExit("jevsor-mcp requires the mcp extra: uvx --from . --with mcp jevsor-mcp") from exc
    server.run()


if __name__ == "__main__":
    main()
