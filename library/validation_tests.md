# Validation test definitions

Each test: what it checks, procedure, **pass/fail criterion with numeric tolerance**, and verification status. Tolerances are defaults; tighten per model. Status tags: `[verified: <where>]` = the criterion has been exercised by a script in this repo; `[unverified]` = defined but not yet run on real models.

Provenance: the *families* of test below (boundary adequacy, structure assessment, dimensional consistency, parameter assessment, extreme conditions, integration error, behaviour reproduction, behaviour anomaly, family member, surprise behaviour, sensitivity, system improvement) are Forrester and Senge's (1980), as adapted and extended in Sterman (2000) §21.4 — see `library/notes/sterman-business-dynamics.md`. The T-numbers, the procedures and **every numeric tolerance here are this repository's own**: neither source states them, so none of them carries any authority but this repo's own tests.

| ID | Test | Pass criterion |
|---|---|---|
| T0 | Translation | fresh PySD translation equals committed `.py` (dependency-key order normalized) |
| T1 | Dimensional consistency | 0 unit errors; every flow = stock unit / time unit |
| T2 | Boundary adequacy | every named feedback loop is endogenous; 0 important exogenous inputs that should respond to the model |
| T3 | Extreme conditions | no negative stocks (min >= -1e-9 x scale); no NaN/inf; behavior matches expected limit |
| T4 | Integration error (dt halving) | max relative change in key outputs < 1% when dt is halved |
| T5 | Behavior reproduction | NRMSE vs reference series <= 10%; peak timing within 5 time steps of the reference run's own dt; correct qualitative mode |
| T6 | Conservation (mass balance) | relative drift of conserved total < 1e-6 |
| T7 | Sensitivity (Monte Carlo) | T7a (gating): Latin hypercube over each parameter's stated range, N >= 1000, 0 failed runs, percentile bands reported. T7b (reported, not gating): policy ranking unchanged in >= 95% of samples |
| T8 | Loop structure and dominance | loops detected in the model = loops declared in the CLD (same variables, same polarity), all scorable; dominance timeline reported; a base run where no loop carries a score at any step fails unless `dominance_empty_at_base` gives the reason |
| T1b | Sector MECE | every model variable in exactly one sector; no two variables with identical equations |
| T1c | Parameter ranges | every parameter has base, low, high; low <= base <= high; [low, high] inside the domain; extreme and policy values inside the domain |

## T0 Translation [verified: engine/tests/test_validate.py test_T0_*, test_translation_drift_detected]
- Procedure: translate the committed `.mdl` afresh with PySD and compare with the committed `.py` (`engine/validate.same_translation`).
- Pass: byte-identical outside the dependency dictionaries (`depends_on` / `other_deps` of `@component.add`, located by parsing the code); inside them, the same keys and counts. Only the key order is normalized, because PySD writes it from Python's per-process string hash, so repeated translations of one `.mdl` can differ there (found 2026-10-29 in `projects/saas-churn-vs-winrate`: 10 translations, 10 distinct files, all equal after this normalization). A changed equation, coefficient, name, unit, comment, non-dependency dict, or an added/removed dependency or changed count still fails. The report says T0 was compared with dependency-key order normalized. Changed with user approval.

## T1 Dimensional consistency [verified: engine/validate.py check_units; engine/tests/test_validate.py catches a deliberate mismatch; 27/27 equations in projects/bass-b2b-adoption]
- Procedure: parse unit strings (`model.doc` in PySD, or Vensim "Units Check"); compute unit of each equation's RHS; compare to LHS. `engine/validate.py` does this on the PySD-translated expressions; a construct it cannot check counts as a failure, not a pass.
- Pass: 0 mismatches. Dimensionless constants must be named, not literal, except 0/1.

## T2 Boundary adequacy [unverified]
- Procedure: list exogenous variables; for each, ask whether the model's own outputs would change it in reality. Re-run with the variable endogenized or replaced by a feedback.
- Pass: no key exogenous variable with a plausible feedback; documented exclusions.

## T3 Extreme conditions [verified: engine/validate.py; 33 cases in projects/bass-b2b-adoption]
- Procedure: set each stock-affecting parameter to 0 and to 10x (and 0.1x); run to final time.
- Pass: no negative stocks beyond -1e-9 x stock scale, no NaN/inf, direction of change matches physical expectation (e.g. zero birth rate -> population does not increase).

## T1c Parameter ranges [verified: engine/tests/test_validate.py test_check_parameters_rules, test_run_all_invalid_spec_is_reported_without_runs]
- Procedure: `engine/validate.check_parameters(spec)` on `validation.toml` before any run. Policy changes are applied unclipped to base, low and high (mul/add/set are monotone, so these bound every Monte Carlo sample).
- Pass: 0 problems. Any problem stops validation before any model run (results withheld). The `[reference]` limit case is exempt: it is set unclipped by design (T5).

## T4 Integration error [verified: engine/verify_archetypes.py]
- Procedure: run at dt and dt/2 (and dt/4); compare outputs on the shared time grid.
- Pass: max relative difference < 1% at dt/2 vs dt (or 1% from the dt/4 reference); for Euler (first order) the error ratio depends on the reference: against the exact solution e(dt)/e(dt/2) = 2 +-10% (verified: ratio 1.97 on the test equation); against the dt/4 run, which is what `validate.py` reports as `euler_error_ratio_dt_vs_dt2`, (x_dt - x_dt/4)/(x_dt/2 - x_dt/4) = (3/4)/(1/4) = 3 +-10% [verified: engine/tests/test_validate.py test_euler_error_ratio_definitions].
- Reasonable first dt: <= tau_min / 4. [unverified rule of thumb]

## T5 Behavior reproduction [verified for analytic limit cases: engine/validate.py, projects/bass-b2b-adoption NRMSE 0.0013 vs closed-form Bass; not yet run against historical data]
- Procedure: compute NRMSE = sqrt(mean((sim-ref)^2)) / (max(ref)-min(ref)).
- Pass: NRMSE <= 0.10, peak time error <= 5 time steps, same mode (growth / S-curve / oscillation / overshoot-collapse).
- Which dt: the reference (limit-case) run's own time step, `[reference].time_step`, or the model dt if the reference sets none. Never the model dt when the reference has its own. A spec may set a tighter peak tolerance, never a looser one. `engine/validate.py` (`peak_tolerance`) fails T5 if the spec's tolerance exceeds 5 x reference dt [verified: engine/tests/test_validate.py test_peak_tolerance_is_five_steps_of_the_reference_dt, test_T5_rejects_a_peak_tolerance_looser_than_the_rule].
- A limit case that keeps a small delay tau inside a loop shifts the peak by about t* x q x tau (Bass with a first-order pipeline). Choose tau from that formula so the predicted shift stays well below 5 reference steps, and keep the reference dt <= tau so Euler integrates the delay without overshoot (see projects/bass-b2b-adoption/t5_audit.md).
- Analytic references available to `[reference].function`: `bass` (args p, q, N) and `goal_seeking` (args G, y0, tau: y = G + (y0 - G) exp(-t/tau), the first-order approach to a goal; added 2026-10-30 with user approval for `projects/car-dealership-profit`, tested by `test_goal_seeking_closed_form_solves_its_ode`). Only the Bass reference has a peak check.
- For the repo's cross-tool models, `raw/test-models/tests/*/output.tab|csv` is the reference. [verified for the existence of references: files present; metric not yet run in bulk]

## T6 Conservation [verified: engine/verify_archetypes.py]
- Procedure: sum the stocks that should conserve (e.g. S+I+R) over time.
- Pass: max |sum(t) - sum(0)| / sum(0) < 1e-6 (verified for SIR with dt = 0.01: well below 1e-6).

## T7 Sensitivity [verified: engine/validate.py, N = 1000 in projects/bass-b2b-adoption]
- Procedure: Latin hypercube over each parameter's stated range and distribution (not a fixed +-25%), N >= 1000 enforced; Spearman rank correlation of each parameter with each output metric; policies run on the same samples (common random numbers).
- T7a pass (gating): 0 failed or non-finite runs; bands P5/P25/P50/P75/P95 reported.
- T7b (reported, not gating): ordering of scenarios by the objective unchanged in >= 95% of samples, plus the share of samples in which the best policy stays best. A model can be valid while a close ranking is not robust; the summary must then say which part of the ranking holds.

## T8 Loop structure and dominance [verified: engine/loop_detector.py; engine/tests/test_loop_detector.py]
- Procedure: enumerate every simple feedback loop in the variable graph of the PySD translation; compute Loops-that-Matter link and loop scores along the base run (method from Schoenberg, Davidsen and Eberlein 2020, reimplemented; exact match with the paper [unverified]).
- Pass: detected loops equal the loops declared in the CLD with the same polarity; every loop scorable (delays written as stocks). Every declared polarity must be `R` or `B` (any other value fails with its own message), and a loop whose polarity is still undetermined, after the `[loop_check]` override where one is declared, fails T8 even if it was declared "undetermined". Added 2026-10-29 with user approval after a review found that string equality accepted loops declared and detected as "undetermined". [verified: engine/tests/test_validate.py test_T8_declared_polarity_must_be_R_or_B_and_undetermined_loops_fail, test_T8_undetermined_loop_fails_without_loop_check]
- Polarity run: polarity is read in the base run, and every loop whose polarity can be read there must match its declaration at base. A link that never changes in the base run has no sign, so a loop through it is "undetermined". When a parameter's base value freezes a link on purpose (an optional effect defaulting to 0), the spec may declare `[loop_check] set = {...}`: **only loops with a zero link at base** then take their polarity from the base run with those overrides, each override inside that parameter's [low, high] (checked by T1c). Scores and the dominance timeline still come from the true base run, and the report names the overrides and the loops they decided. Added 2026-10-29 with user approval for `projects/saas-churn-vs-winrate` (gate 3, option a); narrowed the same day with user approval after a review found that an in-range override could make a loop declared wrongly at base pass. [verified: engine/tests/test_validate.py test_check_parameters_loop_check_rules, test_T8_fails_when_base_freezes_a_loop_link, test_T8_loop_check_reads_polarity_from_override_run, test_T8_loop_check_still_fails_a_wrong_declared_polarity, test_T8_override_cannot_rescue_a_declaration_wrong_at_base, test_T8_override_cannot_break_a_declaration_right_at_base]
- **Empty loop-strength view.** A loop score is the product of its link scores, and a link scores 0 when its input or output does not change, so a base case that freezes one link in every loop gives every loop a score of 0 at every step. The relative score is then `score / sum|score|` with a sum of 0, i.e. NaN everywhere: no dominant loop, and nothing for the explorer's loop-strength chart to draw. `loop_detector.analyze` reports `scored_steps` of `n_steps`, and T8 fails when `scored_steps` is 0 unless the spec gives the reason in `dominance_empty_at_base` (a non-empty string); a declaration made when the view is not empty also fails, so it cannot go stale. Found on `projects/car-dealership-profit`, whose base case sets two effects to 0 that between them sit on a link in all 67 of its loops; the page states the declared reason instead of drawing bands of zero height. [verified: engine/tests/test_validate.py test_T8_fails_when_no_loop_scores_at_base, test_T8_accepts_an_empty_loop_strength_view_when_the_reason_is_declared, test_T8_rejects_a_declaration_that_is_not_needed, test_T8_rejects_a_dominance_declaration_that_is_not_a_reason, test_analyze_counts_the_steps_that_carry_a_loop_score]
- Check of the method: on logistic growth, dominance passes from the R to the B loop at S = 500.45 for K = 1000 (analytic K/2), and Bass shows word of mouth (R) early, saturation (B) late.

## Analytic reference checks used by this repo (all [verified: engine/verify_archetypes.py])
- Exponential growth final value within 1% of e^{gt}.
- Goal seeking within 0.1% of G of the closed form.
- Logistic: inflection at K/2 within 2% of K.
- Bass: peak time within 0.05 time units of ln(q/p)/(p+q); peak stock within 1% of N(q-p)/(2q).
- SIR: peak at S = N/R0 within 2% of N; final size within 0.01 of the implicit solution.
