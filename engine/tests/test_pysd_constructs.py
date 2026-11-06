"""The simulation constructs the engine does not support end to end - material and information delays, TREND,
table functions, test inputs, INITIAL - checked against the cross-tool references committed under raw/test-models.

library/function_compatibility.md listed every one of these as PySD-supported but `[unverified]`. This file is the
evidence behind that tag: each construct below translates with PySD 3.14.3, runs, and reproduces the reference its
own model ships with. It says nothing about whether sd-forge can validate or export such a model - check_units,
loop_detector and export_js all still refuse them, which the last test here pins down.

Tolerance. The references carry 6 significant digits, written by the tool that produced them, so a comparison
against them cannot show less than about 1e-5 relative error (test_exp's reference even records -0.900003 where
-0.9 is exact). EXP and SQRT - constructs the engine already ships and exports - are measured on exactly the same
terms as the control: the tolerance is what the reference files support, not a concession made for the constructs
being added. Each run uses the model's own control values, and every reference time grid is exactly the grid such a
run returns, so nothing is interpolated. The time-control columns the references carry are not compared:
run_batch drops them from the frame.
"""
import glob
import os

import numpy as np
import pandas as pd
import pytest

import export_js as ej
import loop_detector as ld
import validate

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "raw", "test-models", "tests")
REFERENCE_TOL = 1e-5

MATERIAL_DELAYS = [("delays", "DELAY1, DELAY1I, DELAY3, DELAY3I, DELAY N"),
                   ("delay_fixed", "DELAY FIXED"),
                   ("delay_pipeline", "DELAY FIXED, DELAY N"),
                   ("delay_parentheses", "DELAY1"),
                   ("delay_numeric_error", "DELAY N")]

INFORMATION_DELAYS = [("smooth", "SMOOTH, SMOOTHI, SMOOTH3, SMOOTH3I, SMOOTH N"),
                      ("smooth_and_stock", "SMOOTH and SMOOTH3 feeding a stock"),
                      ("trend", "TREND")]

TABLE_FUNCTIONS = [("lookups", "lookup variable called like a function, with a range"),
                   ("lookups_without_range", "lookup variable without a declared range"),
                   ("lookups_inline", "WITH LOOKUP"),
                   ("lookups_inline_bounded", "WITH LOOKUP, bounded"),
                   ("lookups_with_expr", "WITH LOOKUP over an expression"),
                   ("lookups_funcnames", "lookup variable, MODULO")]

INITIALISATION = [("initial_function", "INITIAL"),
                  ("active_initial", "ACTIVE INITIAL"),
                  ("chained_initialization", "one stock's initial value read from another")]

TEST_INPUTS = [("input_functions", "STEP, RAMP, PULSE, PULSE TRAIN")]

# Constructs the engine already translates, validates and exports. Measured here on the same terms, so the
# tolerance can be seen to be a property of the reference files rather than of what is being added.
ALREADY_SUPPORTED = [("abs", "ABS"), ("builtin_max", "MAX"), ("builtin_min", "MIN"),
                     ("logicals", "logical operators and comparisons"), ("time", "TIME")]

# The two that set REFERENCE_TOL: both are exported by the engine today and neither agrees to better than 1e-6.
CONTROL = [("exp", "EXP"), ("sqrt", "SQRT")]

NEEDED = MATERIAL_DELAYS + INFORMATION_DELAYS + TABLE_FUNCTIONS + INITIALISATION + TEST_INPUTS


def reference(case):
    """The committed cross-tool reference frame for a raw/test-models case."""
    d = os.path.join(FIXTURES, case)
    for name, sep in (("output.tab", "\t"), ("output.csv", ",")):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return pd.read_csv(p, sep=sep)
    raise AssertionError(f"{case}: no committed reference (output.tab or output.csv)")


def reproduces(case, tmp_path):
    """Translate and run raw/test-models/tests/<case> and compare with its reference.
    Returns (worst scale-relative difference, the column it was on). The .mdl is copied out before
    translation, so nothing under raw/ is written."""
    mdls = sorted(glob.glob(os.path.join(FIXTURES, case, "*.mdl")))
    assert len(mdls) == 1, f"{case}: expected one .mdl, found {[os.path.basename(m) for m in mdls]}"
    ref = reference(case)
    py = validate.translate(mdls[0], out_dir=str(tmp_path))
    got = validate.run_batch(py, [{}])[0]
    assert got is not None, f"{case}: run failed: {validate.run_batch.last_errors}"

    times = ref["Time"].to_numpy(dtype=float)
    index = np.asarray(got.index, dtype=float)
    assert len(times) == len(index) and np.allclose(times, index, rtol=0, atol=1e-9), \
        f"{case}: the run's time grid is not the reference's ({len(index)} vs {len(times)} points)"

    worst, where = 0.0, None
    compared = 0
    for col in ref.columns:
        # run_batch drops the time controls from the frame; the references still carry them.
        if col == "Time" or col in validate.CONTROL_COLUMNS:
            continue
        assert col in got.columns, f"{case}: the run has no column {col!r}"
        a = pd.to_numeric(ref[col], errors="coerce").to_numpy(dtype=float)
        b = pd.to_numeric(got[col], errors="coerce").to_numpy(dtype=float)
        scale = max(float(np.nanmax(np.abs(a))), 1.0)
        diff = float(np.nanmax(np.abs(a - b))) / scale
        compared += 1
        assert np.isfinite(diff), f"{case}: {col} produced a non-finite difference"
        if diff > worst:
            worst, where = diff, col
    assert compared, f"{case}: the reference has no columns besides Time"
    return worst, where


@pytest.mark.parametrize("case,constructs", NEEDED, ids=[c for c, _ in NEEDED])
def test_construct_reproduces_its_committed_reference(case, constructs, tmp_path):
    worst, where = reproduces(case, tmp_path)
    assert worst <= REFERENCE_TOL, f"{case} ({constructs}): worst column {where!r} differs by {worst:.3g}"


@pytest.mark.parametrize("case,constructs", ALREADY_SUPPORTED, ids=[c for c, _ in ALREADY_SUPPORTED])
def test_an_already_supported_construct_reproduces_its_committed_reference(case, constructs, tmp_path):
    worst, where = reproduces(case, tmp_path)
    assert worst <= REFERENCE_TOL, f"{case} ({constructs}): worst column {where!r} differs by {worst:.3g}"


@pytest.mark.parametrize("case,constructs", CONTROL, ids=[c for c, _ in CONTROL])
def test_an_already_supported_construct_needs_the_same_tolerance(case, constructs, tmp_path):
    """Why REFERENCE_TOL is 1e-5 and not tighter. These two constructs are translated, validated and exported by
    the engine today, so any disagreement here is the reference files' precision rather than the construct's. If
    this stops holding - references regenerated at more digits - tighten REFERENCE_TOL instead of widening it."""
    worst, _ = reproduces(case, tmp_path)
    assert worst <= REFERENCE_TOL
    assert worst > 1e-6, (f"{case} ({constructs}) now agrees to better than 1e-6: the references are more precise "
                          f"than they were, so REFERENCE_TOL can be tightened")


def test_a_stateful_nested_inside_another_statefuls_arguments_disagrees_with_vensim(tmp_path):
    """raw/test-models/tests/arguments writes SMOOTH N(DELAY3(Time, MODULO(constant, 3)), constant, 1, 2): a
    stateful built directly out of another stateful. PySD runs it, and the result is off the reference by far more
    than the reference's precision, while the sibling equation using ABS instead of MODULO agrees. So the nested
    form cannot be validated against PySD - PySD itself does not reproduce it - and a model must name the
    intermediate variable instead. Recorded here so that a change in PySD shows up as a failure."""
    worst, where = reproduces("arguments", tmp_path)
    assert where == "Outer Multiple Middle Multiple Inner Multiple"
    assert 1e-3 < worst < 1e-2, f"the nested-stateful disagreement is now {worst:.3g}, not the recorded ~7e-3"


def test_the_engine_still_refuses_these_constructs(build):
    """The ceiling this file measures from. Until the engine learns them, a model using one of these constructs
    fails T1 units and is refused by the page transpiler, so none of the above is reachable end to end."""
    eqs = [("Input = 10", "Widget"),
           ("Perceived Input = SMOOTH(Input, adjustment time)", "Widget"),
           ("adjustment time = 2", "Month"),
           ("Stock = INTEG(inflow, 0)", "Widget"),
           ("inflow = Perceived Input / adjustment time", "Widget/Month")]
    py = build("smoothing", eqs)

    _, problems = validate.check_units(ld.parse_model(py), "Month")
    assert any("stateful" in p for p in problems), problems

    with pytest.raises(ej.Unsupported):
        ej.load_ir(py)
