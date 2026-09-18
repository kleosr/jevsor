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

## Agent-side contract for `route.decision`

The MCP server returns an envelope. The Cursor agent **must** treat it as binding. Inventing a different action is a contract break.

| `decision` | Agent must | Agent must not |
| --- | --- | --- |
| `proceed` | Act on `routes.*.winner` with Cursor tools. | Re-ask the same heads in chat. Shop for a different option. |
| `confirm` | Show **winner and runner_up** (and `margin`) to the user. Wait for confirmation before mutating tools (edit, shell that writes, deploy). | Treat confirm as proceed. Hide the runner-up. |
| `human` | Stop. Paste the full envelope. No suggested action. The user clarifies state or the question. | Pick the winner anyway. “Escalate” to a stronger model or a nested Cloud Agent. |

`confirm` is not `escalate`. `escalate` (evaluate kwarg) re-asks uncertain heads inside Jevsor. `confirm` is a **user** gate.

## Why disagreement is `human`, not a stronger model

Disagreement between independent evaluations is not a confidence signal. It means the **state is ambiguous or the question is underspecified**. A bigger model gives a second opinion; it does not add the missing fact. Only a human can rewrite the state or the head. Routing disagreement into `escalate` would “optimize” away the invariant. Do not do that.

## Degrade path when MCP is unavailable

Fail-closed default: `{decision: "human", degrade: "human", routes: {}}`. The agent does not roleplay `evaluate`.

Split by **decision class of the action the agent was about to take**, not by model size:

| Class | Examples | If MCP / evaluate is down |
| --- | --- | --- |
| High-risk | rollback, deploy, payments, delete, production data | **Stop.** Tell the user the decision layer is unavailable. No heuristic, no “I’ll just use Composer.” |
| Low-risk | ticket routing, labeling, “which file looks relevant” | Agent **may** fill the same Choice/Score/Noul JSON **once** with the in-IDE model. It must say `degraded=true`, `provenance=prompted`, uncalibrated. It must not call that a Jevsor or measured result. |

There is no third path that invents uniform probabilities.

## Measured-mode backends

In-IDE Cursor models are **always prompted** for Jevsor. Isolated logprobs require a backend that returns `top_logprobs` on a 1-token probe. `debug.measured` is that bit.

| Provider | Default | Measured? |
| --- | --- | --- |
| `stub` | tests | yes (synthetic) |
| `ollama` (local `/v1`, not Ollama Cloud) | llama.cpp-style | usually yes — **this is the real measured path** |
| `openai` / `openai_compat` / `llamacpp` | OpenAI-compatible | probe; many local servers yes, many hosted no |
| `gemini` | probe | 3.x may have withdrawn logprobs |
| `anthropic` | prompted | no, by vendor design |
| `cursor` (Cloud Agents API / SDK) | prompted | **no.** Agent run, not a sampler. `second_harness`. |

You do not get measured mode “for free” inside Cursor chat. Point `JEVSOR_PROVIDER` at Ollama or another logprob endpoint.

## Cloud Agents model sweep (optional, not native)

`evals/cursor_bench.py` can call Composer and Grok 4.6 through the Cloud Agents API. That path is `debug.second_harness`. It cannot satisfy the 70 ms target. Use it only to measure prompted JSON quality.

| Token | Request shape |
| --- | --- |
| `composer-2.5:fast` | `{id: composer-2.5, params: [{id: fast, value: true}]}` |
| `composer-2.5:fast=false` | standard (non-fast) Composer |
| `grok-4.6:low` … `:medium` `:high` `:xhigh` | `{id: grok-4.6, params: [{id: effort, value}]}`. `extra-high` aliases to `xhigh`. |

Discover the account catalog with `GET https://api.cursor.com/v1/models`. Do not assume GPT ids exist. In-IDE, pick these models in Cursor's picker and call MCP — do not nest `Client(provider="cursor")`.

## Probe cache

Capability cache, not answers. Key = SHA-256 prefix of `(provider, model, endpoint)`. Scope = **MCP server process**. Chat session restart typically respawns MCP. Pin versioned model ids when the catalog offers them; a silent weight swap behind `grok-4.6` can stale the bit.

