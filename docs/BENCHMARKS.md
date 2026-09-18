# Benchmarks

Jev's published numbers (70–500 ms, $0.042/MTok, ECE from RLCD, 67.8% workflow mean) are **self-reported and unreproduced**. This file is independent measurement of Jevsor. We do not call hosted Jev.

## What is measured

| Axis | How | What is not a claim |
| --- | --- | --- |
| Latency | Wall time `evaluate` → `route_report`, p50/p95/p99, mean, stdev | Shared-KV fan-out. Isolated mode is N completions. |
| Cost | Input+output tokens × an assumed $/MTok. Stub is $0 and **not** Jev's tariff. Grok 4.6 list price is $2/$6 per MTok ([docs](https://cursor.com/docs/models/grok-4-6)), ~50× the Jev input figure. | Beating $0.042 by using a hash stub. |
| Calibration | ECE on **P(winner)**, 10 bins, ≥100 labeled holdout rows when the run is full. Inverse-entropy ECE is reported separately and is a routing statistic. | RLCD. Silent temperature scaling. |
| Accuracy | Top-1 Choice, Noul threshold 0.5, Score MAE. Labels are constructed in the state text (`evals/holdout.py`, 126 cases), not model agreement. | Stub hash accuracy as a model score. |
| Structural validity | Schema-valid answers / cases. Distinct from decision correctness. | “Zero hallucination” as correctness. |
| Cursor-nativeness | `1` only for MCP-from-agent + stub/Ollama/OpenAI-compat. `provider=cursor` is `0` (`debug.second_harness`). | Nesting Cloud Agents as “native.” |

## Holdout

`evals/holdout.py`: 3 departments × 7 templates × 2 urgency × 3 frustration = **126** cases. Ground truth is written into the ticket string. If you cannot read the ticket, you should score near chance (Choice ~1/3, Noul ~1/2).

## Iteration artifacts

Raw JSON lives under `benchmarks/iteration_N/`. Pareto points: `benchmarks/pareto.json`.

| Iteration | Change | Keep? |
| --- | --- | --- |
| 1 | ECE on P(winner); post-hoc T=4.85 on stub holdout | Keep T as opt-in. Stub accuracy still chance. See `benchmarks/iteration_1/`. |

Temperature scaling is post-hoc on stored distributions. It **must not** change argmax. If a run's `choice_accuracy` moves after T, the implementation is wrong.

## Cursor Cloud Agents

`evals/cursor_bench.py` sweeps `composer-2.5:fast`, `composer-2.5:fast=false`, and `grok-4.6` at effort `low|medium|high|xhigh` when `CURSOR_API_KEY` is set. Each `complete()` is a full agent run (seconds). That sweep **cannot** meet p50 ≤ 70 ms and is nativeness 0. Prior 3-case live file: `evals/results/cursor_live.json` (~13–18 s median).

## How to run

```bash
python3 -m evals.jevbeat --provider stub --write benchmarks/iteration_1/current.json
python3 evals/benchmark.py --check evals/quality_pin.json
# optional, billed:
CURSOR_API_KEY=… python3 evals/cursor_bench.py --write evals/results/cursor_live.json
```
