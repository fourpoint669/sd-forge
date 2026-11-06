# Audit: T5 limit-case change, T4 error ratio, PySD state reset (2026-10-28)

The numbers below were produced by the commands shown and copied from their output. The verdict on A1 belongs to the independent Codex inspector (see the PR description); the host's assessment is given for comparison.

## A1. Was changing the T5 limit case legitimate, or test-fitting?

**What changed.** The project arrived in a single commit (`e5b5df3`), so git holds no earlier version of `validation.toml`. The only record is the comment in its `[reference]` block: with a sales cycle τ = 0.5 months, the first run peaked at 17.0 months against the analytic t* = 15.8, which fails the 1.0-month peak tolerance. τ was then taken to 0.05 months with its own dt = 0.01. The tolerance (1.0 month) and `nrmse_max` (0.10) were not changed.

**Theory.** The limit case is classic Bass only as τ → 0. A pipeline delay τ inside the word-of-mouth loop stretches time by about (1 + q·τ), so t_peak ≈ t*·(1 + q·τ), with q = 1.8/12 = 0.15 per month.

**Run.** A sweep of τ for the reference case, on a scratch copy of `model/` and `validation.toml` (the project was not edited); script and raw output in `audit/a1_tau_sweep.py` and `audit/a1_output.txt`, using `validate.run_batch`, `nrmse`, `bass_cumulative` and `bass_peak_time`:

```
p=0.0116667/month q=0.15/month t*=15.7973; tolerance 1.0 months, nrmse_max 0.1
| tau (months) | dt | t_peak sim | t* | t_peak - t* | t*(1+q*tau) | NRMSE | T5 pass |
|---|---|---|---|---|---|---|---|
| 0.5 | 0.25 | 17.000 | 15.797 | +1.203 | 16.982 | 0.01324 | False |
| 0.5 | 0.01 | 16.930 | 15.797 | +1.133 | 16.982 | 0.01158 | False |
| 0.25 | 0.01 | 16.390 | 15.797 | +0.593 | 16.390 | 0.00605 | True |
| 0.1 | 0.01 | 16.040 | 15.797 | +0.243 | 16.034 | 0.00252 | True |
| 0.05 | 0.01 | 15.920 | 15.797 | +0.123 | 15.916 | 0.00130 | True |
| 0.02 | 0.01 | 15.850 | 15.797 | +0.053 | 15.845 | 0.00057 | True |
| 0.01 | 0.005 | 15.825 | 15.797 | +0.028 | 15.821 | 0.00028 | True |
```

**Reading.**
- The original failure reproduces exactly: τ = 0.5 at the model dt of 0.25 peaks at 17.000.
- The peak offset is proportional to τ (about 2.4·τ months, as t*·q·τ predicts) and goes to 0 as τ → 0. NRMSE falls the same way.
- The prediction t*(1 + q·τ) matches the simulation to within 0.15 months, and to within 0.01 for τ ≤ 0.25.
- τ = 0.05 is not the largest value that passes (τ = 0.25 already passes). The change moved toward the stated limit rather than stopping just inside the tolerance.
- NRMSE passed even at τ = 0.5 (0.013 against 0.10); only the peak check failed.

**Host assessment: legitimate.** The reference describes the τ → 0 limit, and the first run was further from that limit than the comparison assumed. Taking τ closer to 0 removes a known, quantified bias and does not loosen any criterion.

**Flags for the inspector.**
1. The peak tolerance does not match the library rule. `library/validation_tests.md` T5 says "peak timing within ±1 time-step × 5". At the reference dt of 0.01 that is 0.05 months, and the measured offset of 0.123 would fail it. At the model dt of 0.25 it is 1.25. The spec uses 1.0, which is chosen by hand rather than derived from the rule. Changing it needs the user's approval (SKILL.md: never change a threshold without approval), so it was not changed.
2. The reference τ = 0.05 lies below the parameter's domain [0.5, ∞). This is by design: limit cases are set unclipped, and T1c exempts `[reference].set`.

## A2. dt-error ratio: 3 or 2?
Euler is first order: x_h = x + C·h + O(h²).
- Against the dt/4 run (what `validate.py` reports as `euler_error_ratio_dt_vs_dt2`): (x_dt − x_dt/4)/(x_dt/2 − x_dt/4) = (C·dt·3/4)/(C·dt·1/4) = **3**.
- Against the exact solution: e(dt)/e(dt/2) = **2**.

Both values are correct; they use different references. The library line said "2 ± 10%" without naming its reference. It now states both. Measured on exponential decay (`test_euler_error_ratio_definitions`, dt = 0.01, 0.005 and 0.0025): **dt/4-reference ratio 3.0063, exact-reference ratio 2.0042**. In this project's report the ratios are 3.0021 to 3.0327, which is first-order convergence as expected.

## A3. Does the PySD state-reset regression test fail without the fix?
Test: `engine/tests/test_validate.py::test_runs_do_not_inherit_previous_parameters_or_time_step`. Each mutation was applied separately in a throwaway `git worktree` of HEAD `0420174`; the worktree was removed afterwards.

| Code | Result |
|---|---|
| unmutated | `1 passed` |
| M1: worker no longer resets touched parameters to the model's defaults (deletes `params.setdefault(k, v)`) | **FAILED**: `assert np.allclose(a, c)` is False. Run 3 inherited `p = 0` from run 2, so Adopters stays 0. |
| M2: worker passes time controls only when the run sets them (no reset to the model file's dt) | **FAILED**: `ValueError: operands could not be broadcast together with shapes (481,9) (121,9)`. Run 3 inherited dt = 0.25 from run 2. |
| restored | `1 passed` |

The test catches both regressions. Note that M2 surfaces as an error inside `np.allclose` rather than as a clean assertion message; it is still a test failure.

## Refresh
`.venv/bin/python -I engine/validate.py projects/bass-b2b-adoption/validation.toml` exits 0 with `ALL PASS`, run twice in a row. Only `validation_report.md` and `validation_results.json` changed: the new T1c row and empty T4/T6 `problems` lists. `mc_bands.csv`, `policy_results.csv` and `loop_dominance.json` are byte-identical to the committed versions, which is end-to-end evidence that the Monte Carlo is deterministic.

## IR-003 decision (2026-10-29): strict peak rule
**Decision (owner):** the T5 peak tolerance is 5 steps of the reference run's own dt, here 5 x 0.01 = 0.05 months, never the model dt. It must not be loosened. `engine/validate.py` now enforces this: T5 fails if a spec's peak tolerance is looser (`peak_tolerance`, tests `test_peak_tolerance_is_five_steps_of_the_reference_dt`, `test_T5_rejects_a_peak_tolerance_looser_than_the_rule`, `test_project_peak_tolerance_follows_the_rule`). `library/validation_tests.md` states which dt the rule uses.

**Sweep vs formula** (from `audit/a1_output.txt`; predicted peak shift = t* x q x tau = 2.3696 x tau months):

| tau | dt | measured shift | predicted | measured - predicted |
|---|---|---|---|---|
| 0.5 | 0.25 | +1.2027 | +1.1848 | +0.0179 |
| 0.5 | 0.01 | +1.1327 | +1.1848 | -0.0521 |
| 0.25 | 0.01 | +0.5927 | +0.5924 | +0.0003 |
| 0.1 | 0.01 | +0.2427 | +0.2370 | +0.0057 |
| 0.05 | 0.01 | +0.1227 | +0.1185 | +0.0042 |
| 0.02 | 0.01 | +0.0527 | +0.0474 | +0.0053 |
| 0.01 | 0.005 | +0.0277 | +0.0237 | +0.0040 |

The formula reproduces every point to within 0.006 months for tau <= 0.25. The -0.05 at tau = 0.5 is the second-order term. **Where the previous 0.12 came from:** at tau = 0.05 the delay itself shifts the peak by 0.1185 months, and Euler discretisation, with the peak located on the 0.01-month grid, adds another 0.004.

**Choice of tau, from the formula, not from pass/fail:** require the predicted shift to be at most 0.6 x 0.05 = 0.03 (a margin for the observed residual of up to +0.006), so tau <= 0.03 / 2.3696 = 0.0127. Euler integrates the first-order pipeline outflow without overshoot only if dt <= tau, so with the reference dt of 0.01, tau >= 0.01. Hence **tau = 0.01** (predicted shift 0.0237). The reference dt was not changed: the tolerance is defined by it.

**Re-run** (`validate.py`, exit 0, ALL PASS): peak at 15.83 vs t* = 15.7973, **error 0.0327 months** (tolerance 0.05 = rule); NRMSE 0.000318. The residual over the formula (+0.009) is larger than in the sweep (+0.004 to +0.006), as expected at dt = tau, where the Euler delay is coarsest. It still leaves 35% headroom. Monte Carlo outputs are unchanged: the reference run does not feed them.
