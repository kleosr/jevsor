# Limitations

Jevsor copies Jev's **application contract**, not TypeSafe's sampler, RLCD, prices, or latency.

## Not tested here

- Hosted TypeSafe Jev (clean-room: this library never calls it).
- Full Cloud Agents sweeps of grok-4.6 (low…xhigh) × composer on the 126-label holdout. Each `evaluate` is a nested agent run (seconds to tens of seconds). A complete live matrix is a cost/latency experiment, not a 70 ms decision layer. `evals/cursor_bench.py` is the 3-case prompted sweep when `CURSOR_API_KEY` is set.
- Ollama Cloud (logprobs dropped). Local Ollama only when a daemon is present.
- Semantic or answer caches (rejected).

## Hard constraints (not bugs)

- **70 ms p50 on Cursor Cloud Agents is unreachable.** Existing live bench: ~13 s median follow-up on `composer-2.5:fast`. That API is an agent sandbox, not a sampler.
- **$0.042/MTok with free output** is TypeSafe's published Jev price. Cursor Cloud Agent runs are billed as agent usage, not that tariff.
- **ECE ≤ 0.05** needs a calibrated logprob backend plus a held-out fit. Inverse-entropy is a routing statistic; Beat-Jev ECE is P(winner). Temperature scaling is opt-in (`Client(scale_temperature=T)`), never silent, and does not change argmax.
- **≥ 67.8% vs Jev's workflow mean** cannot be claimed against TypeSafe's unpublished labels. Our holdout has **human-constructed ground truth in the state text** (126 cases). Stub accuracy is not a model score. Live Cursor scores on 3 labeled cases exist in `evals/results/cursor_live.json` (9/9 heads) and are too small to beat a 67.8% claim.
- **Cursor-nativeness = 1** only for MCP-from-agent + stub/Ollama/OpenAI-compat. `provider="cursor"` is a second harness (`debug.second_harness`).

## Assumptions

- Question ids never go to the model.
- Isolated logprobs require `top_logprobs` on the **MCP process** backend.
- Probe cache is `(provider, model, endpoint)` capability bits in the MCP process.
- Disagreement → human, not a bigger model.

## What would be needed to verify further

- A local llama.cpp/Ollama box for measured ECE on the 126-label set.
- A Cursor completions API with logprobs (does not exist in public docs).
- TypeSafe's workflow JSON, if they publish it, for an apples-to-apples accuracy number — still without calling their sampler.
