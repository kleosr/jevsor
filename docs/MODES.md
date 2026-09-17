# Modes

## batch

Default. Independent questions should be asked together.

- **Prompted providers:** one JSON object with every answer. Cheap. Questions *can* see each other in the prompt — documented divergence from Jev isolation.
- **Logprobs providers:** v0.1 still issues one measured single-token call per question. We do not pretend we share a KV cache.

## isolated

One concurrent call per question. Strict isolation, N× state cost.

Default failure mode is **all-or-nothing**: the first fatal error cancels siblings and raises. Partial answers are not in v0.1.

Concurrency is semaphore-bounded (default 8). Local servers have finite slots; raise `JEVSOR` load slowly.

## When to pay N×

Use isolated when cross-talk would change the decision (adversarial options, calibration studies, independent verification). Use batch prompted when you want one round trip and can live with prompt interference.

## Speculative heads

Not in the core library. Pattern: ask operation + candidate targets in one request, then execute the matching head in code. See `examples/composite_routing.py`.
