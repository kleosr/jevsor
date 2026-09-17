---
name: jevsor
description: >
  Typed Jev-compatible decisions over gathered state. Use when you need Choice,
  Score, or Boolean judgments, confidence-gated routing, or an evaluate tool
  instead of a free-form agent loop.
---

# jevsor

Reproduce Jev's harness, not TypeSafe's model. Code owns control flow. The model
answers only narrow common-sense questions over unstructured state.

## Rules

- Assemble **thin state** first (files already read, diffs, facts). Do not pad.
- Ask the **narrowest atomic typed questions**: Choice, Score, or Noul/Boolean.
- Put many independent questions in **one** `evaluate` call. Combine in code.
- Thresholds live in your code (`route_band`, per-action bars). Not in the prompt.
- Every answer has `provenance`: `measured` (logprobs) or `prompted` (JSON).
  Do not average them. If `mixed_provenance` is true, treat the response as mixed.
- Isolated mode costs N round trips. Batch prompted can cross-talk. See honesty.
- Do not launch a subagent per boolean. Do not claim Jev latency or calibration.
- Question **keys are ids only** — never instructions.

## Tool

Call MCP `evaluate` (stdio server: `uvx --from . --with mcp jevsor-mcp`) with `state` plus a `questions` map. Expect `answers` keyed
by the same ids, plus `usage` and `debug`.

```json
{
  "state": {"ticket": "Payouts failing 3 days"},
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
  "provider": "stub",
  "fanout": "isolated"
}
```

Route on `confidence` for Choice/Score (Noul has none — use `noul` as P(yes)):

- high → act
- mid → confirm
- low → human

Plot confidence against accuracy on your labels before production thresholds.
