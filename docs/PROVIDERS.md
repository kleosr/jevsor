# Providers

v0.1 matrix. Static rows are *defaults*. A 1-token logprobs probe on first use overwrites the row for `(provider, model)`.

| Provider | Constructor | Default mode | Notes |
|---|---|---|---|
| `stub` | `Client("stub")` | measured | Deterministic. Tests and examples. |
| `ollama` | `Client("ollama", model="llama3.1")` | measured | Local `http://127.0.0.1:11434/v1`. Not Ollama Cloud. |
| `openai` / `openai_compat` | `Client("openai", model="gpt-4.1-mini")` | measured | `OPENAI_API_KEY`, optional `OPENAI_BASE_URL`. |
| `llamacpp` | `Client("llamacpp", model="...", base_url="http://127.0.0.1:8080/v1")` | measured | llama.cpp server. |
| `gemini` | `Client("gemini", model="gemini-2.5-flash")` | probed | `GEMINI_API_KEY`. 3.x may have withdrawn logprobs → prompted. |
| `anthropic` | `Client("anthropic", model="claude-sonnet-4-5")` | prompted | No logprobs by vendor design. `ANTHROPIC_API_KEY`. |
| `cursor` | `Client("cursor", model="composer-2.5:fast")` | prompted | **Last-resort backend.** Cloud Agents API (`CURSOR_API_KEY`, `https://api.cursor.com`) launches a full agent, not a logprob sampler. Sets `debug.second_harness`. Prefer MCP `evaluate` inside Cursor. `composer-2.5:fast` / `composer-2.5:fast=false`. Grok effort: `grok-4.6:low` … `grok-4.6:xhigh` (`extra-high` aliases to `xhigh`). Discover params with `GET /v1/models`. |

Remote `base_url` is opt-in. Keys come from the environment or constructor, never from the repo.

Live tests are skipped unless you pass `--live`. Each live skip names the missing daemon or key.
