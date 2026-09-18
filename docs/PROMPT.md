# Beat-Jev prompt (iteration 1)

Self-evolving prompt after the native-split + route-envelope work. Constraints below are **pins**, not suggestions.

## Objective

A Cursor-native decision layer (Jevsor) that beats TypeSafe Jev on independently measured axes. Do not call hosted Jev.

| Axis | Weight | Target |
| --- | --- | --- |
| Latency p50 (MCP `evaluate`→route, batch ≥10) | 25% | ≤ 70 ms |
| Cost | 20% | ≤ $0.042 / MTok input-equivalent |
| ECE on P(winner), ≥100 labeled | 25% | ≤ 0.05 |
| Accuracy, labeled System One tasks | 20% | ≥ 67.8% |
| Cursor-nativeness | 10% | 1 (no second harness, no private APIs) |

## Pins learned (do not regress)

1. **No second harness.** Cursor owns the agent loop. Jevsor is MCP `evaluate` + `route`. `Client(provider="cursor")` is nativeness 0.
2. **No private Cursor internals.** No sampler, KV cache, router weights, or raw in-IDE completions. Cursor SDK / Cloud Agents API do not expose logprobs.
3. **In-IDE is always prompted JSON.** Measured mode needs a backend that returns `top_logprobs` (local Ollama / llama.cpp / some OpenAI-compat). Document it; do not claim measured “for free” in Cursor.
4. **No averaging as calibration.** Consensus via `verify` + `debug.disagreed` only. Disagreement → `human`, **not** a stronger model. Ambiguity is not a confidence signal; escalation does not add the missing fact.
5. **Deterministic composition.** Models judge; code routes. `proceed` / `confirm` / `human` is an agent contract (`docs/CURSOR.md`).
6. **Honest latency.** Isolated = N completions. Prompted batch = one JSON. Cloud Agents = one sandbox run per `complete()`, seconds not milliseconds.
7. **Probe cache is a capability bit.** Key = SHA-256(`provider`, `model`, `endpoint`) in the **MCP process**. Not an answer cache. Pin versioned model ids.
8. **Fail closed.** `{decision: human, degrade: human, routes: {}}`. High-risk: stop. Low-risk: one in-IDE prompted JSON labeled `degraded=true`, never called Jevsor/measured.
9. **ECE ≠ inverse-entropy.** Score ECE on P(winner). Inverse-entropy is for `route_band` only.
10. **Temperature scaling does not change argmax.** Do not use it as an accuracy intervention. Fit T on a held-out split; never auto-apply in production without an explicit `scale_temperature`.
11. **Stub accuracy is not a model score.** The stub hashes the prompt. Chance-level Choice is expected. Do not “optimize” the stub to keyword-match labels.
12. **Do not claim termination** while Cloud Agents are the backend, or while ECE/accuracy are measured only on the stub.

## Architecture (baseline, keep)

Choice / Score / Noul; keys-as-ids; measured vs prompted; inverse-entropy for routing; auto fan-out; gated speculative heads; confidence escalate vs route `confirm`; verify without replace; MCP evaluate+route; fail-closed; opt-in T-scaling.

## Loop

Measure (`evals/jevbeat.py`) → weakest axis → falsifiable hypothesis → minimal patch + tests → re-measure → Pareto (`benchmarks/pareto.json`) → update this file.

If three iterations fail the same axis, escalate structurally (logprob backend, tree-Noul, isotonic, binary decomposition). Do not escalate disagreement to a bigger model.

## Termination

All five targets true under independent labels, honest latency, nativeness 1. Then stop.

## Deliverable

`docs/ARCHITECTURE.md`, `docs/CURSOR.md`, `docs/BENCHMARKS.md`, `docs/LIMITATIONS.md`, this file, tests, no extra harness.
