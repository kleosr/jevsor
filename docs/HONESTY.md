# Honesty

jevsor copies Jev's *application contract*, not TypeSafe's sampler.

## Divergences that will not go away

1. **No shared-KV fan-out.** Isolated mode is N round trips. Batch mode is one prompted JSON call (questions can attend to each other) or, when logprobs work, N single-token measured calls. There is no free parallel readout.
2. **Measured ≠ prompted.** Logprob distributions are model likelihoods over tokens. Prompted distributions are verbalized guesses. They are not interchangeable, not averageable, and the eval harness bins metrics by `provenance`.
3. **Uncalibrated until you measure.** There is no RLCD. `confidence` is jevsor's inverse-entropy statistic (`1 - H(p)/log(K)`), labeled as ours because TypeSafe's formula is unpublished. Run `evals/calibration.py` on *your* labels before trusting a threshold. Temperature fitting is reported, never auto-applied.
4. **Cost is the caller's.** We do not reproduce $0.042/MTok or 70–500ms. Usage is whatever the provider billed.
5. **Schema is validated in code.** Jev binds the schema at the sampler. We retry malformed JSON a bounded number of times, then raise.

## Truncation

`top_logprobs` is typically capped at 20. Choice allows 255 options. When options exceed the measurable alphabet, jevsor takes the labeled **wide-choice** path (independent P(fit) per option, then normalize) and sets `truncated: true`. Missing token mass is `missing_mass`, never silently redistributed as if it were observed.

## Clean room

No TypeSafe SDK, API key, weights, or ToS-licensed code. Public docs only. Compare against hosted Jev yourself if you hold a key; this library will not call it.
