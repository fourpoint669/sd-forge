# Gate 7 validation log

Record of every gate 7 run, failure, diagnosis and fix. `validation_report.md` and `validation_results.json` are
rewritten by `engine/validate.py` on every run; this log keeps the history.

## Run 1 (2026-10-29, commit 3964188): FAIL on T0; results withheld

Command: `.venv/bin/python -I engine/validate.py projects/saas-churn-vs-winrate/validation.toml`, exit 1.
`checks.py` was **not** run: the user's instruction for gate 7 is to stop and report on any failure.

| Test | Result | Measured | Limit |
|---|---|---|---|
| **T0 translation** | **FAIL** | committed `.py` differs from a fresh translation of the `.mdl` | identical |
| T1 units | pass | 90 variables, 0 problems | 0 |
| T1b MECE | pass | 0 problems | 0 |
| T1c parameter ranges | pass | 0 problems | 0 |
| T3 extremes | pass | 112 cases, 0 failures | 0 |
| T4 dt halving | pass | max relative change 0.001822 (corner, Cumulative Revenue) | < 0.01 |
| T5 behavior | pass | NRMSE 0.000389; peak error 0.0327 months | NRMSE <= 0.10; peak <= 0.05 (5 x dt 0.01) |
| T6 conservation | pass | max relative drift 6.943e-15 | < 1e-6 |
| T7 Monte Carlo | pass | N = 1000 per scenario, 0 failed runs | N >= 1000, 0 failed |
| T8 loops | pass | 22 found = 22 declared, 0 problems (polarity from the `[loop_check]` run) | equal |

T7b (ranking stability) is a result and stays unreported while validation fails.

### Diagnosis of T0
- **The difference is dict ordering only.** The single diff is the position of `"customer_share": 1` inside the
  `depends_on` dict of `word of mouth starts`. The equations are identical.
- **The translation is not deterministic for this model.** Ten fresh translations of the unchanged `.mdl` gave
  **10 distinct files**. After sorting the keys of every dict literal (AST comparison), all ten are **identical** to
  the committed `.py`.
- **Cause: per-process hash randomization.** PySD collects dependencies into a structure whose order follows
  Python's per-process string hash seed. `validate.translate` runs PySD in a `python -I` worker, and `-I` ignores
  `PYTHONHASHSEED`, so even `PYTHONHASHSEED=0` gave three distinct outputs.
- **Affected components:** six have an unstable `depends_on` order: `word of mouth starts`, `CS coverage`, `ARR per
  customer`, `expansion headroom`, `sales capacity` and `effective win rate`. All use `MAX(...)`, a parenthesised
  product, or `a + b * c`.
- **The worked example is not affected.** Five fresh translations of `bass-b2b-adoption` were byte-identical to its
  committed `.py`; its equations have none of these shapes.
- **Conclusion:** T0 fails here because the translator's output order changes from run to run, not because the
  committed `.py` drifted from the `.mdl`. A re-run could pass or fail by chance (6 components x several orderings).
  It is not a model error.

### Options (none applied; awaiting the user's decision)
1. **Engine change (recommended): T0 compares translations up to dict-literal key order.** It parses both files and
   sorts the keys of every dict literal before comparing ASTs. Any change to an equation, a name, a unit or a value
   still fails. Needs approval, plus tests: a reordered `depends_on` passes, and a changed coefficient still fails.
2. **Engine change: pin the worker's hash seed.** Start the translation worker with a fixed hash seed (needs an
   environment change for `-I` workers). This keeps byte-identical comparison, but relies on PySD staying
   deterministic for a fixed seed, which is untested.
3. **Model rewrite to avoid the unstable shapes.** Fragile: which expression shapes PySD orders stably is not known.
   `effective win rate` (`a + b * c`) varies while the example's `deal closings * (1 - win rate)` does not.

Not acceptable under the gate rules: re-running until T0 passes by chance, or dropping T0.

### Fix applied (user approved option 1, with limits)
Engine commit `3bdf5b5`, separate from project files: `engine/validate.same_translation` locates the dependency
dictionaries (`depends_on` / `other_deps` of `@component.add`) by parsing the code. Outside them both files must
match byte for byte. Inside them the same keys and counts must appear, and only their order may differ.
- **Tests written first, each seen failing:**
  - reordered keys pass;
  - nested `other_deps` reordered passes;
  - each of these fails: changed coefficient, added dependency, removed dependency, changed dependency count,
    reordered non-dependency dict, changed comment;
  - end to end, a reordered committed `.py` passes, and the report states the comparison mode.
- **Each test was run against a stub that should fail it, and did:**
  - byte equality fails the 2 reorder tests;
  - always-true fails the 6 difference tests;
  - sorting every dict fails the non-dependency-dict and comment tests.
- `bass-b2b-adoption` T0 still passes, run through `run_all` on a scratch copy (all its tests pass there; its
  committed files are untouched).
- The full engine suite passes: 135 tests.
- The model and the committed `.py` were **not** changed. All ten earlier fresh translations equal the committed
  `.py` under the new comparison; none is byte-equal.
- Documented in `library/validation_tests.md` (T0). No tolerance, range or other test changed.

## Run 2 (2026-10-29, engine 3bdf5b5, model 3964188): PASS; results released

`engine/validate.py` exit 0, then `checks.py` exit 0 (it appended its section to `validation_report.md`).

| Test | Result | Measured | Limit |
|---|---|---|---|
| T0 translation | pass | identical, compared with dependency-key order normalized | identical |
| T1 units | pass | 90 variables, 0 problems | 0 |
| T1b MECE | pass | 0 problems | 0 |
| T1c parameter ranges | pass | 0 problems | 0 |
| T3 extremes | pass | 112 cases, 0 failures | 0 |
| T4 dt halving | pass | max relative change 0.001822 (corner, Cumulative Revenue); Euler error ratio 3.00-3.03 | < 0.01 |
| T5 behavior | pass | NRMSE 0.000389; evaluation-starts peak 15.83 months, error 0.0327 months | NRMSE <= 0.10; peak <= 0.05 (5 x 0.01) |
| T6 conservation | pass | max relative drift 6.94e-15 (Monte Carlo max; base 5.5e-16, corner 2.9e-15) | < 1e-6 |
| T7 Monte Carlo | pass | N = 1000 per scenario (6 scenarios), 0 failed runs | N >= 1000, 0 failed |
| T7b ranking stability | reported, not gating | full ranking stable in 60.4% of samples; best policy stable in 67.5% | (>= 95% = robust) |
| T8 loops | pass | 22 found = 22 declared, 0 problems (polarity from the `[loop_check]` run, C = 1) | equal |
| checks.py regression vs bass-b2b-adoption | pass | Customers max abs diff 0 Firm over 481 steps (bit-identical) | <= 1e-9 relative |
| checks.py ARR identity, base | pass | max gap 1.86e-08 USD/Year, relative 7.4e-16 | < 1e-6 |
| checks.py ARR identity, corner | pass | max gap 7.45e-08 USD/Year, relative 8.07e-16 | < 1e-6 |

## After gate 7 approval (2026-10-29)

### Mutation test for checks.py
`projects/saas-churn-vs-winrate/test_checks.py` (run: `.venv/bin/python -I -m pytest projects/saas-churn-vs-winrate/test_checks.py -q`;
3 passed). Each case copies the `.mdl`, mutates it, translates the copy, and calls `checks.regression` on it.

| Case | Mutation | Regression check | Max abs diff in Customers | Relative (limit 1e-9) |
|---|---|---|---|---|
| control | none | pass | 0 Firm | 0 |
| mutant 1 | CS Capacity starts at 50 firms instead of 0, so churn falls even with zero budget | **fails** | 0.377 Firm | 2.7e-4 |
| mutant 2 | negative word-of-mouth term kept alive by a +0.5 offset on the multiplier | **fails** | 17.9 Firm | 1.3e-2 |

Mutant 1 shows that even a small, fading departure (the extra capacity decays over the 4-month ramp) is caught,
by about five orders of magnitude.

### Engine test count reconciliation
Collected with `pytest --collect-only` at each commit (temporary worktrees):

| Commit | Tests | Change |
|---|---|---|
| `cfdaa3e` (main) | 122 | baseline |
| `cc9028f` `[loop_check]` | 126 | +4: `test_check_parameters_loop_check_rules`, `test_T8_fails_when_base_freezes_a_loop_link`, `test_T8_loop_check_reads_polarity_from_override_run`, `test_T8_loop_check_still_fails_a_wrong_declared_polarity` |
| `3bdf5b5` T0 fix | 135 | +9: reordered keys (1), nested `other_deps` (1), six difference cases (6), end to end (1) |

Removed or replaced between `main` and `3bdf5b5`: **none**. The "10 T0 tests" figure came from a run with
`-k "T0_ or translation_drift"`, which also picked up the existing `test_translation_drift_detected`.

## External review (Codex), 2026-10-29: findings and fixes
The user approved fixes for findings 1 and 3-7. Finding 2 (a missing test) is covered by the finding 1 tests.

| # | Finding | Fix |
|---|---|---|
| 1 | An in-range `[loop_check]` override could make a loop declared wrongly at base pass T8 (base q = -0.01 reverses the word-of-mouth loops; override q = 0.38 matched the declarations) | Engine commit `9681a59`: polarity is read in the base run; the override decides only loops with a zero link at base. Tests first, both seen failing. Engine suite 137 passed; `bass-b2b-adoption` passes on a scratch copy |
| 2 | No test covered "wrong at base, right under the override" | `test_T8_override_cannot_rescue_a_declaration_wrong_at_base`, plus the reverse case |
| 3 | `08_policy.md` credited all 875 never-flipping samples to win rate first | Now 841 stay win rate first and 34 stay churn first (in both documents) |
| 4 | Seven cells in the summary ARR table were rounded wrongly | The table is now generated from `scenario_bands.csv`, rounding half up; exactly those seven cells changed |
| 5 | k\* P25 and P75 (30/30) were rounded wrongly | 0.31 -> 0.30 and 0.83 -> 0.82 (from 0.30499 and 0.82494) |
| 6 | Difference-chart figures had no source in the evidence files | `gate9_difference_chart.py` writes them to `order_difference_summary.json` (computed from `order_difference_bands.csv`); the summary cites each key |
| 7 | Customer-loop dominance intervals in the summary did not match the JSON | Now 0.25-8.5 (R1) and 8.75-120 (B3), citing `dominance_customer_loops_base_run`, in both documents |

**Re-run after the engine fix (model unchanged):** `validate.py` exit 0, then `checks.py` exit 0. T8 passes with
polarity taken from `[loop_check]` only for B12 and B13, the two parameter-C loops; the other 20 are read at base.
`validation_results.json` and `loop_dominance.json` changed only by the new `polarity_source` /
`polarity_from_loop_check` fields (24 leaves, no numbers).

**Search for the same errors elsewhere.** A script recomputed 89 quoted figures in `summary.md` and `08_policy.md`
from `gate8_results.json`, `validation_results.json` and `order_difference_summary.json`. Every figure matched, except
four that were artifacts of the checker (line wrapping, word order). One presentational fix came out of it: the 30/30
k\* drivers are now listed strongest first. Also removed: an unsupported claim in the summary's "Beyond 5 years" row
(that the expansion ceiling limits growth), which no result supports.

## External review (Codex), round 2, 2026-10-29: findings and fixes
The user approved fixes for findings 1-5.

| # | Finding | Fix |
|---|---|---|
| 1 | T8 compared polarity strings, so loops declared and detected as "undetermined" passed (Bass q = 0, override q = 0) | Engine commit `731659b`: a declared polarity must be R or B, and a loop still undetermined after `[loop_check]` (or at base without it) fails. Tests first, both seen failing. Engine suite 139 passed; `bass-b2b-adoption` passes on a scratch copy; this project's T8: 22 found = 22 declared, 0 problems; outputs byte-identical |
| 2 | `08_policy.md` said parameter C has \|Spearman\| <= 0.06; the largest is 0.0603 | Now "about 0.06 at most; the largest is 0.060, for win rate only - 50/50" |
| 3 | Configured inputs (A = B = C = 0, capacity 45 with range 20-120, budget range, parameter bounds) had no cited source among the result files | Both documents now cite `validation.toml` and `assumptions_register.md` for configured inputs, in the header and at each place they appear |
| 4 | Falsification numbers had no stated source; the NRR 97-114% statement did not say what it measures | The table labels each value as a benchmark input (configured range, `sources.md` / `assumptions_register.md`) or a model result (`gate8_results.json`). The NRR row now defines NRR, gives the base value (~101%) and the benchmark quartile range 97-114%, and states the wider 83.5-116.2% range from sampling churn and expansion independently, with separate actions for observations inside and outside it |
| 5 | PySD 3.14.3 and an earlier-draft median (0.39) were not established by the evidence | The summary cites `engine/requirements.txt` (pins `pysd==3.14.3`) for the version; the earlier-draft sentence is removed from `08_policy.md` |

Figure check rerun: 89 quoted figures recomputed from the result files; all match (three misses are the known
checker artifacts of line wrapping and wording).
