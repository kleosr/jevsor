"""Cursor Cloud Agents API prompted provider. Not logprobs, not Token Harbor."""

from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx

from jevsor.errors import AuthError, ProviderError, RateLimitError
from jevsor.providers.base import Completion

DEFAULT_CURSOR = "https://api.cursor.com"
TERMINAL = {"FINISHED", "ERROR", "CANCELLED", "EXPIRED"}


def _json_from_text(text: str) -> dict[str, Any] | None:
    raw = text.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        inner = [ln for ln in lines[1:] if not ln.strip().startswith("```")]
        raw = "\n".join(inner).strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            parsed = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def _model_payload(model: str) -> dict[str, Any]:
    if ":" not in model:
        return {"id": model}
    ident, _, flag = model.partition(":")
    return {"id": ident, "params": [{"id": flag, "value": "true"}]}


def _extract_text(run: dict[str, Any], conversation: dict[str, Any] | None) -> str:
    for key in ("result", "summary", "text"):
        value = run.get(key)
        if isinstance(value, str) and value.strip():
            return value
    messages = (conversation or {}).get("messages") or []
    for message in reversed(messages):
        role = str(message.get("type") or message.get("role") or "")
        if role.lower() in {"assistant", "agent"}:
            text = message.get("text") or message.get("content")
            if isinstance(text, str) and text.strip():
                return text
            if isinstance(text, list):
                bits = [str(p.get("text", "")) for p in text if isinstance(p, dict)]
                joined = "".join(bits).strip()
                if joined:
                    return joined
    return json.dumps(run)


class CursorAgentProvider:
    name = "cursor"

    def __init__(
        self,
        model: str,
        *,
        api_key: str | None = None,
        timeout: float = 180.0,
        name: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.model = model
        if name:
            self.name = name
        self.api_key = api_key if api_key is not None else os.environ.get("CURSOR_API_KEY", "")
        self.timeout = timeout
        self.base_url = (base_url or DEFAULT_CURSOR).rstrip("/")
        self._http = httpx.Client(timeout=timeout)
        self._agent_id: str | None = None

    def _headers(self) -> dict[str, str]:
        return {
            "authorization": f"Bearer {self.api_key}",
            "content-type": "application/json",
        }

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self._http.request(
            method, f"{self.base_url}{path}", headers=self._headers(), **kwargs
        )
        if response.status_code == 401:
            raise AuthError("CURSOR_API_KEY rejected")
        if response.status_code == 429:
            raise RateLimitError(response.text)
        if response.status_code >= 400:
            raise ProviderError(response.text, status=response.status_code)
        if not response.content:
            return {}
        data = response.json()
        return data if isinstance(data, dict) else {}

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
        del max_tokens, temperature, logprobs, top_logprobs, schema, seed
        if not self.api_key:
            raise AuthError("CURSOR_API_KEY is missing")
        body = "\n\n".join(f"{m['role']}: {m['content']}" for m in messages)
        prompt = (
            "Do not use tools. Do not read or edit files. "
            "Reply with a single JSON object only.\n\n"
            f"{body}"
        )
        if self._agent_id is None:
            created = self._request(
                "POST",
                "/v1/agents",
                json={
                    "prompt": {"text": prompt},
                    "model": _model_payload(self.model),
                    "name": f"jevsor-{self.model}"[:100],
                },
            )
            agent = created.get("agent") or created
            run = created.get("run") or {}
            self._agent_id = str(agent.get("id") or "")
            run_id = str(run.get("id") or agent.get("latestRunId") or "")
        else:
            self._wait_idle()
            created = self._post_run(prompt)
            run = created.get("run") or created
            run_id = str(run.get("id") or "")
        if not self._agent_id or not run_id:
            raise ProviderError(f"cursor create missing ids: {created}")
        finished = self._wait(self._agent_id, run_id)
        self._wait_idle()
        conversation = None
        try:
            conversation = self._request("GET", f"/v1/agents/{self._agent_id}/conversation")
        except ProviderError:
            conversation = None
        text = _extract_text(finished, conversation)
        parsed = _json_from_text(text)
        return Completion(text=text, parsed=parsed)

    def _post_run(self, prompt: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.timeout
        last_exc: Exception | None = None
        while time.monotonic() < deadline:
            try:
                return self._request(
                    "POST",
                    f"/v1/agents/{self._agent_id}/runs",
                    json={"prompt": {"text": prompt}},
                )
            except ProviderError as exc:
                last_exc = exc
                if "agent_busy" not in str(exc):
                    raise
                time.sleep(3)
        raise ProviderError(f"cursor agent stayed busy: {last_exc}")

    def _wait_idle(self) -> None:
        if not self._agent_id:
            return
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            agent = self._request("GET", f"/v1/agents/{self._agent_id}")
            body = agent.get("agent") or agent
            run_id = str(body.get("latestRunId") or "")
            if not run_id:
                return
            run = self._request("GET", f"/v1/agents/{self._agent_id}/runs/{run_id}")
            status = str((run.get("run") or run).get("status") or "").upper()
            if status in TERMINAL or not status:
                return
            time.sleep(2)

    def _wait(self, agent_id: str, run_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.timeout
        last: dict[str, Any] = {}
        while time.monotonic() < deadline:
            last = self._request("GET", f"/v1/agents/{agent_id}/runs/{run_id}")
            run = last.get("run") or last
            status = str(run.get("status") or "").upper()
            if status in TERMINAL:
                if status != "FINISHED":
                    raise ProviderError(f"cursor run {status}: {run}")
                return run
            time.sleep(2)
        raise ProviderError(f"cursor run timed out: {last}")

    def probe_logprobs(self) -> bool:
        return False

    def close(self) -> None:
        if self._agent_id:
            try:
                self._request("DELETE", f"/v1/agents/{self._agent_id}")
            except Exception:
                try:
                    self._request("POST", f"/v1/agents/{self._agent_id}/archive")
                except Exception:
                    pass
        self._http.close()
