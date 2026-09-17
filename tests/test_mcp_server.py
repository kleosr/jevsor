from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from jevsor.errors import ValidationError
from jevsor.mcp_server import evaluate_payload

ROOT = Path(__file__).resolve().parents[1]


def test_evaluate_tool_offline() -> None:
    result = evaluate_payload(
        "payouts failing three days",
        {
            "dept": {
                "type": "choice",
                "instructions": "Which team?",
                "criteria": {"billing": "money", "tech": "bugs"},
            },
            "urg": {"type": "noul", "instructions": "Urgent?"},
        },
        provider="stub",
        model="stub",
        fanout="isolated",
    )
    assert "answers" in result
    assert result["answers"]["dept"]["type"] == "choice"
    assert result["answers"]["urg"]["type"] == "noul"
    assert "error" not in result


def test_evaluate_tool_validation_error() -> None:
    with pytest.raises(ValidationError):
        evaluate_payload("x", {}, provider="stub")


def test_import_writes_no_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    import jevsor.mcp_server as mod

    del mod
    captured = capsys.readouterr()
    assert captured.out == ""


def test_stdio_subprocess_emits_only_jsonrpc() -> None:
    pytest.importorskip("mcp")
    proc = subprocess.Popen(
        [sys.executable, "-c", "from jevsor.mcp_server import main; main()"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(ROOT),
        text=True,
    )
    init = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "jevsor-test", "version": "0"},
        },
    }
    assert proc.stdin is not None and proc.stdout is not None
    try:
        out, _err = proc.communicate(json.dumps(init) + "\n", timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
        pytest.fail("mcp server produced no stdout within 15s")
    line = (out or "").splitlines()[0] if out else ""
    assert line.startswith("{"), line
    payload = json.loads(line)
    assert payload.get("jsonrpc") == "2.0"


@pytest.mark.asyncio
async def test_in_memory_list_and_call() -> None:
    mcp = pytest.importorskip("mcp")
    from mcp.shared.memory import create_connected_server_and_client_session

    from jevsor.mcp_server import create_server

    server = create_server()
    async with create_connected_server_and_client_session(server._mcp_server) as session:
        tools = await session.list_tools()
        names = [t.name for t in tools.tools]
        assert "evaluate" in names
        called = await session.call_tool(
            "evaluate",
            {
                "state": "hello",
                "questions": {"u": {"type": "noul", "instructions": "Greeting?"}},
                "provider": "stub",
                "model": "stub",
            },
        )
        assert called.isError is False
        text = called.content[0].text
        body = json.loads(text)
        assert body["answers"]["u"]["type"] == "noul"

    del mcp
