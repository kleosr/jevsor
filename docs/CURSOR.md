# Cursor

Jevsor is a **decision layer** the Cursor agent calls. It does not replace Cursor's harness.

Supported integration is an [Agent Plugin](https://agent-plugins.org/plugin-authors): skill + MCP (`evaluate`, `route`). No Cursor-only rules or hooks — those already exist natively.

The native loop:

1. The Cursor agent gathers **thin state** with native tools (read, grep, index, terminal).
2. It calls MCP `evaluate` with Choice / Score / Noul heads (plus speculative heads when useful).
3. It calls MCP `route` (or `route_band` in Python) and branches in code.
4. It executes side effects with Cursor tools. Hooks still deny/allow.

Do **not** launch a Cloud Agent or a Task subagent per boolean. Do **not** point `Client(provider="cursor")` at the in-IDE model. The [Cloud Agents API](https://cursor.com/docs/cloud-agent/api/endpoints) and [Cursor SDK](https://cursor.com/docs/sdk/python) run full agents, not raw completions. That path is a last-resort prompted backend and sets `debug.second_harness`.

Cursor Router / Auto routes **agent turns**. It is not a per-question Jevsor router. Leave it alone.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the split, keep/modify table, and unsupported internals.

## Local load

1. Install [uv](https://docs.astral.sh/uv/). From this checkout: `uv sync --extra mcp`.
2. Copy or symlink this repo's `plugin/` directory to `~/.cursor/plugins/local/jevsor`.
3. Point the plugin MCP `uvx --from` at the **checkout**, not the plugin copy. Either run Cursor with this repo as the workspace (so `--from .` resolves), or set the copied `mcp.json` args to `--directory <checkout> --from . --with mcp>=1.27,<2 jevsor-mcp`.
4. Reload Cursor.
5. Confirm in **Customize**: skill `jevsor` is listed.
6. Confirm in **Settings → MCP**: `jevsor` has a green dot.
7. In chat: ask the agent to `evaluate` a ticket with a Choice and a Noul, then `route` the answers. Expect `decision` (`proceed` / `confirm` / `human`) plus per-head `winner` / `runner_up`. On tool failure expect `degrade: "human"`, not invented probabilities.

On failure, read the **Output** panel MCP channel before editing server code.

## Inspector smoke (optional, needs Node)

```bash
uv sync --extra mcp
npx -y @modelcontextprotocol/inspector --cli -- --config plugin/mcp.json --server jevsor --method tools/list --cwd . --format json
bash tests/inspector_smoke.sh
```

Quality pin (client path and MCP `evaluate` must match):

```bash
uv run python evals/benchmark.py --check evals/quality_pin.json
```

## Variables

Do not put keys in the plugin. Set `JEVSOR_PROVIDER`, `JEVSOR_MODEL`, and provider keys in the environment or the plugin dashboard `${VAR}` slots.

For in-IDE use, prefer `stub` (tests), local Ollama, or an OpenAI-compatible endpoint. `JEVSOR_PROVIDER=cursor` starts a nested Cloud Agent per `evaluate` and is the wrong default.

Marketplace submission needs a public repo and Cursor review — deferred.
