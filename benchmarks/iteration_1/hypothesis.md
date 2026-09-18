# Hypothesis — iteration 1

**Statement:** Fitting a single temperature on 26 labeled Choice distributions and applying it post-hoc to the remaining 100 will reduce ECE on P(winner) from 0.1314 to ≤ 0.06 without changing top-1 Choice accuracy, because softmax(log p / T) does not change argmax (rounding must not retie the winner).

**Why this and not accuracy:** the stub hashes the prompt. Keyword-matching the stub would fake accuracy. Temperature scaling is the correct first move when calibration is the weakest axis.

**Falsify if:** ECE on the 100-row eval split stays > 0.06, or Choice accuracy on that split moves after T, or `rounded_argmax_flips` is treated as a new winner.

**Non-goals:** auto-applying T in `Client` (opt-in only); claiming the stub beat Jev; using Cloud Agents for this axis (nativeness 0, seconds not milliseconds).
