# Verdict — iteration 1

**Confirmed** for calibration on the stub. **Do not claim Jev is beaten.**

- Fitted T = 4.85 (flatten — the hash stub is overconfident vs ~1/3 accuracy).
- ECE P(winner) on 100 held-out rows: **0.0205** (≤ 0.05).
- Choice accuracy on that split: **0.33** (chance). Original argmax kept; 13/100 rows would have flipped if rounded softmax were allowed to retie — those flips are reported, not used as winners.
- Latency unchanged (post-hoc). Structural validity still 1.0.

Keep: opt-in `Client(scale_temperature=T)` and post-hoc fit. Do **not** auto-apply T in production.

**Next weakest axis: accuracy.** A real model is required. Native path is a logprob backend (Ollama/llama.cpp). Cursor Cloud Agents (Composer, Grok 4.6 low→xhigh) are a prompted second-harness sweep: useful for JSON quality, nativeness 0, cannot meet 70 ms.

Constraint for iteration 2: do not keyword-hack the stub; do not treat T-scaling as an accuracy lever; do not put `provider=cursor` on the native Pareto frontier.
