# Cursor

jevsor ships as an [Agent Plugin](https://agent-plugins.org/plugin-authors): skill + MCP server, no Cursor-only rules/hooks.

Launch the server with **uvx**, not pip.

## Local load

1. Install [uv](https://docs.astral.sh/uv/). From this checkout: `uv sync --extra mcp`.
2. Copy or symlink this repo's `plugin/` directory to `~/.cursor/plugins/local/jevsor`.
3. Point the plugin MCP `uvx --from` at the **checkout**, not the plugin copy. Either run Cursor with this repo as the workspace (so `--from .` resolves), or set the copied `mcp.json` args to `--directory <checkout> --from . --with mcp>=1.27,<2 jevsor-mcp`.
4. Reload Cursor.
5. Confirm in **Customize**: skill `jevsor` is listed.
6. Confirm in **Settings → MCP**: `jevsor` has a green dot.
7. In chat: ask the agent to `evaluate` a ticket with a Choice and a Noul. Expect Jev-shaped `answers` plus `debug`.

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

Marketplace submission needs a public repo and Cursor review — deferred.
