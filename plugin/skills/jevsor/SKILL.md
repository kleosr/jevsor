---
name: jevsor
description: >
  Typed Jev-compatible decisions over gathered state. Use when you need Choice,
  Score, or Boolean judgments, confidence-gated routing, or an evaluate tool
  instead of a free-form agent loop.
---

# jevsor

Jevsor is a decision layer on top of Cursor, not a second agent. Cursor already
owns context retrieval, indexing, tools, rules, hooks, and model selection.
You gather thin state with native tools, then call MCP `evaluate`.

## Native loop

1. **Gather state with Cursor tools** (read, grep, list, terminal). Facts only. Do not pad.
2. **Ask the narrowest atomic typed questions** in one `evaluate` call: Choice, Score, Noul/Boolean.
3. Put maybe-needed heads in `speculative` with a `when` gate. Do not make a second agent turn to ask them.
4. Call MCP `route` on the `answers`, passing `disagreed` from `debug` when present. Branch on `decision`: proceed / confirm / human. Use `winner` and `runner_up`; do not invent a threshold.
5. **Execute with Cursor tools.** Thresholds and side effects stay out of the prompt.

## Failure

- If `evaluate` or `route` returns `degrade: "human"` (or an `error`), stop. Decision is human. Do not fill in probabilities yourself.
- If the `jevsor` MCP server is missing or unreachable, say so and ask the user. Do not roleplay an evaluate.
- Isolated logprobs only exist if `debug.measured` is true. In Cursor chat that is usually false: the in-IDE model is not a logprob API. Prompted JSON is the native path.
- Do not average `measured` and `prompted`. If `debug.disagreed` is nonempty, `route` already treats those heads as human.

## Rules

- Do not launch a subagent or Cloud Agent per boolean.
- Do not call `Client(provider="cursor")` from inside Cursor chat. That nests a full Cloud Agent. The in-IDE model is already running; Jevsor is the MCP tool.
- Do not re-index the repo or re-implement grep/read. Cursor already does that.
- Do not invent confidence thresholds. Use `route` / `route_band`. Stakes raise the bar.
- Question **keys are ids only** — never instructions.
- Every answer has `provenance`: `measured` (logprobs) or `prompted` (JSON). Do not average them. If `mixed_provenance` is true, treat the response as mixed.
- Isolated mode costs N round trips. Batch prompted can cross-talk. `auto` picks for you.
- `debug.second_harness` means someone used the Cloud Agents API as a completion backend. Avoid that in-IDE.
- Do not claim Jev latency, Jev calibration, or a shared KV cache.

## Tool

Call MCP `evaluate` (stdio server: `uvx --from . --with mcp jevsor-mcp`).

```json
{
  "state": {"ticket": "Payouts failing 3 days", "diff": "...already read..."},
  "questions": {
    "dept": {
      "type": "choice",
      "instructions": "Which team should handle this?",
      "criteria": {
        "billing": "Payments, invoices, refunds",
        "tech": "Bugs, outages"
      }
    },
    "urgent": {
      "type": "noul",
      "instructions": "Does this convey urgency?"
    }
  },
  "speculative": {
    "severity": {
      "type": "score",
      "instructions": "How severe is the outage?",
      "criteria": ["Cosmetic", "Degraded", "Blocking"]
    }
  },
  "when": {
    "severity": {"question": "dept", "equals": "tech"}
  },
  "fanout": "auto",
  "escalate": "confirm"
}
```

Then `route` the `answers` (pass `debug.disagreed`). Branch on `decision`: `proceed` / `confirm` / `human`. If `degrade` is `human`, stop.

Plot confidence against accuracy on your labels before production thresholds.
