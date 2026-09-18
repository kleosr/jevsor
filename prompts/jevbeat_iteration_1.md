# Beat-Jev prompt after iteration 1

Copy of `docs/PROMPT.md` plus what this iteration proved.

## Confirmed

- ECE must be P(winner). Inverse-entropy ECE on the stub was 0.261 vs 0.131 max-prob.
- Temperature scaling on a chance-level stub **flattens** (T≈4.85) and can put ECE ≤ 0.05 while accuracy stays ~1/3. That is calibration of a random hasher, not a Jev win.
- Rounding can retie argmax. Preserve the original Choice. Report flips; do not take them as new winners.
- Probe cache: SHA-256(provider, model, endpoint), MCP process.
- Cloud Agents catalog (this account): `grok-4.6` effort {low,medium,high,xhigh} + fast; `composer-2.5` fast. Default Grok is high+fast. Default Composer is fast.

## Rejected / do not retry

- Keyword-matching the stub to inflate accuracy.
- Auto-applying T in the client.
- Treating Cloud Agents as the 70 ms / nativeness-1 path.
- Escalating disagreement to a stronger model.

## Iteration 2 focus

**Accuracy**, with a real backend. Native: Ollama/llama.cpp logprobs. Optional measurement-only: Composer + Grok 4.6 low→xhigh via Cloud Agents (nativeness 0, record p50 in seconds).
