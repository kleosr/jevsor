# Weakest axis — iteration 1

Source: `benchmarks/iteration_1/current.json` (stub, fanout=auto, 126 labeled holdout cases).

| Axis | Measured | Target | Relative miss |
| --- | --- | --- | --- |
| Latency p50 | 0.609 ms | ≤ 70 ms | none (stub, in-process) |
| Cost | $0 assumed | ≤ $0.042/MTok | not comparable (hash stub, not a model) |
| ECE P(winner) | 0.1314 | ≤ 0.05 | **largest** (0.1314/0.05 − 1 = 1.63) |
| Accuracy (Choice+Noul mean) | 0.3651 | ≥ 0.678 | 0.678/0.3651 − 1 = 0.86 |
| Nativeness | 1 | 1 | none |

**Focus: calibration.**

Caveats: stub Choice 0.2857 and Noul 0.4444 are chance-level. Structural validity is 1.0. Inverse-entropy ECE was 0.2612 — do not use it as the Beat-Jev ECE axis. Isolated mode is 3 in-process heads per case, not hidden HTTP.
