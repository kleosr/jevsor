"""MCP stdio server. One tool: evaluate. stdout is JSON-RPC only."""

from __future__ import annotations

import os
from typing import Any

from jevsor.contract import Question
from jevsor.errors import JevsorError
from jevsor.runner import Client, Fanout
from jevsor.validate import parse_request


def evaluate_payload(
    state: Any,
    questions: dict[str, Any],
    *,
    provider: str | None = None,
    model: str | None = None,
    fanout: Fanout = "batch",
) -> dict[str, Any]:
    kind = provider or os.environ.get("JEVSOR_PROVIDER", "stub")
    name = model or os.environ.get("JEVSOR_MODEL", "stub")
    req = parse_request({"state": state, "questions": questions})
    parsed: dict[str, Question] = req.questions
    with Client(provider=kind, model=name, fanout=fanout) as client:
        response = client.evaluate(state=req.state, questions=parsed)
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
    ) -> dict[str, Any]:
        """Evaluate state against a Jev-shaped questions map. Returns answers plus debug."""
        mode: Fanout = "isolated" if fanout == "isolated" else "batch"
        try:
            return evaluate_payload(
                state, questions, provider=provider, model=model, fanout=mode
            )
        except JevsorError as exc:
            return {"error": str(exc), "status": exc.status}

    return server


def main() -> None:
    try:
        server = create_server()
    except ImportError as exc:
        raise SystemExit("jevsor-mcp requires the mcp extra: uvx --from . --with mcp jevsor-mcp") from exc
    server.run()


if __name__ == "__main__":
    main()
