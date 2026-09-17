# Modes

`auto` (recommended): prompted models use one JSON batch; logprob models use isolated single-token heads. This is the LLM analogue of Jev's parallel readout, not a shared KV cache.

## batch

Prompted providers: one JSON object with every answer, including speculative heads. Cheap. Questions *can* see each other in the prompt — documented divergence from Jev isolation.

If the provider actually supports logprobs, `batch` still resolves to isolated measured heads. We do not pretend a JSON object is a logprob distribution.

## isolated

One concurrent call per question. Strict isolation, N× state cost.

Default failure mode is **all-or-nothing**: the first fatal error cancels siblings and raises. Partial answers are not in v0.1.

Concurrency is semaphore-bounded (default 8). Local servers have finite slots; raise `JEVSOR` load slowly.

Speculative heads are **gated**. They run in a second isolated wave only when `when` matches a core answer. Unconditional speculative heads run in the first wave.

## escalate / verify

Opt-in. Not a second agent.

- `escalate="confirm"`: isolated re-ask of confirm/human heads only (cheap-first).
- `escalate="human"`: only the human band.
- `verify=True`: independent isolated pass; flags `debug.disagreed`; does **not** replace answers.

## When to pay N×

Use isolated when cross-talk would change the decision (adversarial options, calibration studies, independent verification). Use batch prompted when you want one round trip and can live with prompt interference. Use `auto` unless you have a reason.

## Speculative heads

Pass `speculative={...}` plus optional `when={qid: {question, equals|noul_gte|score_gte|band}}`.

On prompted batch, extra heads go in the same JSON (Jev-like). On isolated measured, extra heads that fail their gate are skipped (`debug.skipped_speculative`). Combine remaining answers in code — see `examples/composite_routing.py`.
