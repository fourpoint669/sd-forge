"""engine/validate.py: each check must catch a deliberately broken model and pass a correct one."""
import math
import os
import textwrap

import numpy as np
import pytest

import loop_detector as ld
import validate
from conftest import BASS, LOGISTIC, SPEC, mdl_text


# ---------------------------------------------------------------- T1 units
def test_units_pass_on_consistent_model(build):
    n, probs = validate.check_units(ld.parse_model(build("bass", BASS)), "Month")
    assert n == 9 and probs == []


def test_units_catch_mismatch(build):
    bad = [("Stock = INTEG(inflow, initial stock)", "Widget"), ("initial stock = 1", "Widget"),
           ("inflow = rate * Stock", "Widget"),            # should be Widget/Month
           ("rate = 0.1", "1/Month"),
           ("mixed = Stock + rate", "Widget")]              # adds Widget to 1/Month
    _, probs = validate.check_units(ld.parse_model(build("badunits", bad)), "Month")
    text = " ".join(probs)
    assert any(p.startswith("inflow:") for p in probs)
    assert any(p.startswith("mixed:") for p in probs)
    assert any(p.startswith("Stock:") for p in probs), text   # flow x time != stock


def test_units_missing_is_an_error(build):
    eqs = [("Stock = INTEG(inflow, initial stock)", "Widget"), ("initial stock = 1", "Widget"), ("inflow = 1", "")]
    _, probs = validate.check_units(ld.parse_model(build("nounits", eqs)), "Month")
    assert any("missing units" in p for p in probs)


@pytest.mark.parametrize("s,expect", [
    ("Firm/Month", {"Firm": 1, "Month": -1}), ("1/Month", {"Month": -1}), ("Dmnl", {}),
    ("$/(Firm*Month)", {"$": 1, "Firm": -1, "Month": -1}), ("Month/Year", {"Month": 1, "Year": -1}),
    ("m^2", {"m": 2})])
def test_parse_units(s, expect):
    assert validate.parse_units(s) == expect


# ---------------------------------------------------------------- T1b MECE
def test_mece_catches_overlap_gap_and_duplicates(build):
    eqs = BASS + [("adoption copy = adoption from advertising + adoption from word of mouth", "Person/Month")]
    m = ld.parse_model(build("mece", eqs))
    sectors = {"market": ["Potential Adopters", "Adopters", "total population", "adopter fraction"],
               "adoption": ["adoption", "adoption from advertising", "adoption from word of mouth", "p", "q", "Adopters"]}
    probs = validate.check_mece(m, sectors)
    assert any("'Adopters' in 2 sectors" in p for p in probs)
    assert any("'adoption copy' in no sector" in p for p in probs)
    assert any("identical equations" in p for p in probs)


# ---------------------------------------------------------------- T4 dt halving
DECAY = [("Level = INTEG(-drain, initial level)", "Litre"), ("initial level = 100", "Litre"),
         ("drain = Level / drain time", "Litre/Month"), ("drain time = 1", "Month")]


def test_dt_halving_fails_with_coarse_step_and_passes_with_fine(build):
    py = build("decay", DECAY, final_time=8, time_step=0.5)
    runs = [{"time_step": dt, "saveper": 0.5} for dt in (0.5, 0.25, 0.01, 0.005)]
    a, b, c, d = validate.run_batch(py, runs)
    assert validate.dt_change(a, b, ["Level"])["Level"] > validate.DT_TOL
    assert validate.dt_change(c, d, ["Level"])["Level"] < validate.DT_TOL


# ---------------------------------------------------------------- T6 conservation
def test_conservation_catches_leak(build):
    eqs = [("A = INTEG(-transfer, initial A)", "Item"), ("initial A = 100", "Item"),
           ("B = INTEG(transfer * arrival fraction, 0)", "Item"),
           ("transfer = A * transfer rate", "Item/Month"), ("transfer rate = 0.2", "1/Month"),
           ("arrival fraction = 0.9", "Dmnl")]
    py = build("leak", eqs)
    tight, leaky = validate.run_batch(py, [{"params": {"arrival fraction": 1}}, {}])
    g = [{"name": "total", "stocks": ["A", "B"]}]
    assert validate.conservation_drift(tight, g) < validate.CONS_TOL
    assert validate.conservation_drift(leaky, g) > 0.01


# ---------------------------------------------------------------- T3 extremes
def test_extreme_check_flags_negative_stock(build):
    eqs = [("Cash = INTEG(-spending, initial cash)", "Dollar"), ("initial cash = 10", "Dollar"),
           ("spending = spend rate", "Dollar/Month"), ("spend rate = 5", "Dollar/Month")]
    df = validate.run_batch(build("neg", eqs), [{}])[0]
    ok, v = validate.check_expect(df, {"var": "Cash", "stat": "min", "op": ">=", "value": 0})
    assert not ok and v < 0


def test_expectation_dsl():
    import pandas as pd
    df = pd.DataFrame({"x": [0.0, 1, 3, 3]}, index=[0.0, 1, 2, 3])
    assert validate.check_expect(df, {"var": "x", "stat": "monotone_nondecreasing"})[0]
    assert not validate.check_expect(df, {"var": "x", "stat": "monotone_nonincreasing"})[0]
    assert validate.check_expect(df, {"var": "x", "stat": "final", "op": "==", "value": 3})[0]
    assert validate.stat(df["x"], df.index, {"stat": "time_to_reach", "value": 2}) == 2.0
    assert validate.stat(df["x"], df.index, {"stat": "value_at", "time": 1.5}) == 2.0


# ---------------------------------------------------------------- T5 helpers
def test_nrmse_hand_computed():
    # errors (0, 1, -1, 0): RMSE = sqrt(0.5); range of ref = 3
    assert math.isclose(validate.nrmse([0, 2, 1, 3], [0, 1, 2, 3]), math.sqrt(0.5) / 3)


def test_bass_closed_form_matches_archetype_peak():
    p, q, N = 0.03, 0.38, 1000
    t = np.linspace(0, 30, 30001)
    a = validate.bass_cumulative(t, p, q, N)
    rate = np.gradient(a, t)
    assert abs(t[np.argmax(rate)] - validate.bass_peak_time(p, q)) < 0.01
    assert abs(a[np.argmax(rate)] - N * (q - p) / (2 * q)) / N < 0.001


def test_goal_seeking_closed_form_solves_its_ode():
    G, y0, tau = 237.5, 40.0, 1.5
    t = np.linspace(0, 30, 300001)
    y = validate.goal_seeking(t, G, y0, tau)
    assert y[0] == y0 and abs(y[-1] - G) < 1e-3
    # y' = (G - y)/tau at every point (central difference), and 63.2% of the gap closes in one tau
    assert np.max(np.abs(np.gradient(y, t)[1:-1] - (G - y[1:-1]) / tau)) < 1e-3
    assert math.isclose(validate.goal_seeking(tau, G, y0, tau), G + (y0 - G) / math.e)
    assert validate.ANALYTIC["goal_seeking"] is validate.goal_seeking


@pytest.mark.parametrize("y,mode", [
    (np.ones(50), "constant"),
    (np.exp(np.linspace(0, 3, 50)), "growth"),
    (1 / (1 + np.exp(-np.linspace(-6, 6, 50))), "s-curve"),
    (np.exp(-((np.linspace(0, 10, 50) - 5) ** 2)), "peak"),
    (np.sin(np.linspace(0, 6 * np.pi, 200)), "oscillation"),
    (np.exp(-np.linspace(0, 3, 50)), "decline")])
def test_mode_classifier(y, mode):
    assert validate.classify_mode(y) == mode


# ---------------------------------------------------------------- worker isolation
def test_runs_do_not_inherit_previous_parameters_or_time_step(build):
    py = build("bassiso", BASS, final_time=30, time_step=0.0625)
    a, b, c = validate.run_batch(py, [{}, {"params": {"p": 0.0}, "time_step": 0.25}, {}], workers=1)
    assert b["Adopters"].iloc[-1] < a["Adopters"].iloc[-1]
    assert np.allclose(a.to_numpy(), c.to_numpy()) and a.index.equals(c.index)


# ---------------------------------------------------------------- T7 Monte Carlo + end to end


def test_monte_carlo_refuses_small_n(bass_project):
    spec, R, _ = validate.run_all(str(bass_project / "validation.toml"), n=999)
    assert R["tests"]["T7_monte_carlo"]["pass"] is False
    assert R["tests"]["T7_monte_carlo"]["detail"] == "N = 999 < 1000"
    assert not R["all_pass"]


def test_lhs_reproducible_and_in_range(bass_project):
    spec = validate.load_spec(str(bass_project / "validation.toml"))
    n1, s1 = validate.lhs_samples(spec, 50, seed=3)
    _, s2 = validate.lhs_samples(spec, 50, seed=3)
    assert s1 == s2 and n1 == ["p", "q", "total population"]
    assert all(0.01 <= s["p"] <= 0.05 and 500 <= s["total population"] <= 2000 for s in s1)


def test_end_to_end_pass_and_results_released(bass_project):
    spec, R, res = validate.run_all(str(bass_project / "validation.toml"))
    T = R["tests"]
    assert R["all_pass"], {k: v for k, v in T.items() if not v["pass"]}
    assert T["T4_dt_halving"]["max_rel_change"] < 0.01
    assert max(T["T6_conservation"]["max_rel_drift"].values()) < 1e-6
    assert T["T5_behavior"]["nrmse"] < 0.01
    assert T["T7_monte_carlo"]["n"] == 1000 and T["T7_monte_carlo"]["failed_runs"] == 0
    assert T["T8_loops"]["n_loops"] == 3
    validate.write_outputs(spec, R, res)
    assert (bass_project / "mc_bands.csv").exists()
    header = (bass_project / "mc_bands.csv").read_text().splitlines()[0]
    assert header.startswith("time,Adopters|P5,Adopters|P25,Adopters|P50,Adopters|P75,Adopters|P95,adoption|P5")
    assert "WITHHELD" not in (bass_project / "validation_report.md").read_text()


def test_results_withheld_when_a_test_fails(bass_project):
    spec_path = bass_project / "validation.toml"
    spec_path.write_text(SPEC.replace('polarity = "R"', 'polarity = "B"'))   # wrong declared polarity
    spec, R, res = validate.run_all(str(spec_path))
    assert R["tests"]["T8_loops"]["pass"] is False and not R["all_pass"]
    validate.write_outputs(spec, R, res)
    assert not (bass_project / "mc_bands.csv").exists()
    assert "WITHHELD" in (bass_project / "validation_report.md").read_text()


def test_T5_reports_q_below_p_peak_and_report_renders(bass_project):
    spec_path = bass_project / "validation.toml"
    spec_path.write_text(SPEC.replace('function = "bass"', 'function = "bass"\nset = { p = 0.5, q = 0.1 }'))
    spec, R, res = validate.run_all(str(spec_path), n=999)
    t5 = R["tests"]["T5_behavior"]
    assert t5["pass"] is False
    assert "q > p" in t5["peak"]["error"]
    validate.write_outputs(spec, R, res)
    report = (bass_project / "validation_report.md").read_text()
    assert "q > p" in report and "WITHHELD" in report


def test_translation_drift_detected(bass_project):
    py = bass_project / "bass.py"
    py.write_text(py.read_text().replace("return 0.38", "return 0.39"))
    _, R, _ = validate.run_all(str(bass_project / "validation.toml"))
    assert R["tests"]["T0_translation"]["pass"] is False


def test_worker_timeout_reported(bass_project, monkeypatch):
    monkeypatch.setattr(validate, "TIMEOUT_BASE_S", 0.001)
    out = validate.run_batch(str(bass_project / "bass.py"), [{}], timeout_per_run=0)
    assert out == [None]
    assert any("timeout" in str(e) for e in validate.run_batch.last_errors)


# ---------------------------------------------------------------- T1c parameter ranges
def _spec_dict(text=None):
    import tomllib
    return tomllib.loads(text or SPEC)


def _set(d, path, value):
    *head, last = path
    for k in head:
        d = d[k]
    if value is _DEL:
        del d[last]
    else:
        d[last] = value


_DEL = object()
_EXT = "no advertising and no adopters: nobody adopts"


@pytest.mark.parametrize("edits,message", [
    ([(("parameters", "p", "base"), _DEL)], "p: missing base"),
    ([(("parameters", "p", "high"), _DEL)], "p: missing high"),
    ([(("parameters", "p", "low"), 0.05), (("parameters", "p", "high"), 0.01)], "p: low 0.05 > high 0.01"),
    ([(("parameters", "p", "base"), 0.08)], "p: base 0.08 outside [low, high] = [0.01, 0.05]"),
    ([(("parameters", "q", "domain"), [0, 0.4])], "q: range [0.3, 0.5] outside domain [0, 0.4]"),
    ([(("parameters", "total population", "low"), 0)], "total population: loguniform needs low > 0"),
    ([(("extreme", 0, "set"), {"p": 2})], f"extreme '{_EXT}': p = 2 outside domain [0, 1]"),
    ([(("extreme", 0, "set"), {"r": 0})], f"extreme '{_EXT}': unknown parameter 'r'"),
    ([(("policies", 1, "changes"), {"p": {"mul": 30}})], "policy 'more advertising': p reaches 1.5 outside domain [0, 1]"),
    ([(("policies", 1, "changes"), {"r": {"mul": 2}})], "policy 'more advertising': unknown parameter 'r'"),
])
def test_check_parameters_rules(edits, message):
    spec = _spec_dict()
    for path, value in edits:
        _set(spec, path, value)
    probs = validate.check_parameters(spec)
    assert message in probs, probs


def test_check_parameters_accepts_bass_fixture_spec():
    assert validate.check_parameters(_spec_dict()) == []


def test_check_parameters_accepts_project_spec():
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    spec = validate.load_spec(os.path.join(root, "projects", "bass-b2b-adoption", "validation.toml"))
    assert validate.check_parameters(spec) == []


def test_run_all_fails_T1c_on_base_outside_range(bass_project):
    spec_path = bass_project / "validation.toml"
    _, R, _ = validate.run_all(str(spec_path), n=999)                       # control
    assert R["tests"]["T1c_parameter_ranges"]["pass"] is True
    spec_path.write_text(SPEC.replace("base = 0.03\n", "base = 0.08\n"))
    _, R, _ = validate.run_all(str(spec_path), n=999)
    t = R["tests"]["T1c_parameter_ranges"]
    assert t["pass"] is False and "p: base 0.08 outside [low, high] = [0.01, 0.05]" in t["problems"]


RELEASE = ("mc_bands.csv", "policy_results.csv", "loop_dominance.json")


@pytest.mark.parametrize("old,new,message", [
    ("base = 0.03\n", "", "p: missing base"),
    ("high = 0.05\n", "", "p: missing high"),
    ("set = { p = 0 }", "set = { r = 0 }", f"extreme '{_EXT}': unknown parameter 'r'"),
    ("base = 0.03\n", "base = 0\n", "p: base 0 outside [low, high] = [0.01, 0.05]"),
])
def test_run_all_invalid_spec_is_reported_without_runs(bass_project, monkeypatch, old, new, message):
    spec_path = bass_project / "validation.toml"
    spec_path.write_text(SPEC.replace(old, new))
    for f in RELEASE:                                   # results released by an earlier passing run
        (bass_project / f).write_text("stale")

    def no_runs(*a, **k):
        raise AssertionError("no model run may happen on an invalid spec")
    monkeypatch.setattr(validate, "run_batch", no_runs)
    spec, R, res = validate.run_all(str(spec_path), n=999)
    t = R["tests"]["T1c_parameter_ranges"]
    assert t["pass"] is False and message in t["problems"]
    assert R["fatal"].startswith("parameter specification invalid") and R["all_pass"] is False
    validate.write_outputs(spec, R, res)
    report = (bass_project / "validation_report.md").read_text()
    assert "Fatal:" in report and "WITHHELD" in report
    assert not any((bass_project / f).exists() for f in RELEASE)


def test_main_contains_unexpected_exception(bass_project, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(validate, "run_all", boom)
    assert validate.main([str(bass_project / "validation.toml")]) == 1
    report = (bass_project / "validation_report.md").read_text()
    assert "RuntimeError: boom" in report and "WITHHELD" in report


# ---------------------------------------------------------------- T7 Monte Carlo determinism and failures
from conftest import make_project  # noqa: E402

SPEC_NOPOL = SPEC.split("\n[policy]")[0] + "\n"


def _mc_args(spec):
    m = spec["model"]
    model = ld.parse_model(m["py_path"])
    time_kw = {"final_time": m["final_time"], "time_step": m["time_step"], "saveper": m.get("saveper", 1)}
    return (m["py_path"], m["key_outputs"], [c.name for c in model.stocks], spec.get("conservation", []), time_kw)


@pytest.fixture(scope="module")
def mc_pair(tmp_path_factory):
    d = make_project(tmp_path_factory.mktemp("mc") / "proj", BASS, SPEC_NOPOL, final_time=30, time_step=0.0625)
    spec = validate.load_spec(str(d / "validation.toml"))
    py, key, stocks, groups, time_kw = _mc_args(spec)
    one = validate.monte_carlo(spec, py, 1000, 7, key, stocks, groups, time_kw, workers=1)
    four = validate.monte_carlo(spec, py, 1000, 7, key, stocks, groups, time_kw, workers=4)
    return one, four


def test_monte_carlo_identical_across_reruns_and_workers(mc_pair):
    one, four = mc_pair
    assert one["failed"] == 0 and four["failed"] == 0
    assert one["bands"] == four["bands"] and one["band_time"] == four["band_time"]
    assert one["metric_pct"] == four["metric_pct"]
    for k in one["spearman"]:
        a = np.array(list(one["spearman"][k].values()), float)
        b = np.array(list(four["spearman"][k].values()), float)
        assert np.array_equal(a, b, equal_nan=True)


def test_lhs_seed_changes_samples(bass_project):
    spec = validate.load_spec(str(bass_project / "validation.toml"))
    _, s7 = validate.lhs_samples(spec, 50, seed=7)
    _, s8 = validate.lhs_samples(spec, 50, seed=8)
    assert s7 != s8
    for s in s7 + s8:
        assert 0.01 <= s["p"] <= 0.05 and 0.3 <= s["q"] <= 0.5 and 500 <= s["total population"] <= 2000


def test_bands_are_ordered_percentiles(mc_pair):
    one, _ = mc_pair
    for c, b in one["bands"].items():
        arr = np.array([b[p] for p in ("P5", "P25", "P50", "P75", "P95")])
        assert np.all(np.diff(arr, axis=0) >= 0), c
        assert arr.shape[1] == len(one["band_time"])


@pytest.mark.parametrize("seed_line", ["", "seed = 7.5\n", "seed = true\n"])
def test_monte_carlo_requires_integer_seed(bass_project, seed_line):
    spec_path = bass_project / "validation.toml"
    spec_path.write_text(SPEC.replace("seed = 7\n", seed_line))
    _, R, res = validate.run_all(str(spec_path), n=1000)
    t7 = R["tests"]["T7_monte_carlo"]
    assert t7["pass"] is False and t7["detail"] == "montecarlo.seed must be an integer"
    assert res is None and not R["all_pass"]


def _failing_mc(monkeypatch, every):
    real = validate.run_batch

    def fake(py, runs, workers=None, **kw):
        if not (runs and runs[0].get("return_columns")):
            return real(py, runs, workers, **kw)           # deterministic runs: untouched
        keep = [i for i in range(len(runs)) if every and i % every == 0]
        got = real(py, [runs[i] for i in keep], workers, **kw) if keep else []
        out = [None] * len(runs)
        for i, df in zip(keep, got):
            out[i] = df
        return out
    fake.last_errors = []
    monkeypatch.setattr(validate, "run_batch", fake)


@pytest.mark.parametrize("every,failed", [(0, 1000), (2, 500)])
def test_monte_carlo_failures_are_reported(bass_project, monkeypatch, every, failed):
    spec_path = bass_project / "validation.toml"
    spec_path.write_text(SPEC_NOPOL)
    _failing_mc(monkeypatch, every)
    spec, R, res = validate.run_all(str(spec_path))
    t7 = R["tests"]["T7_monte_carlo"]
    assert t7["pass"] is False and t7["failed_runs"] == failed
    if failed == 1000:
        assert t7["detail"] == "no successful Monte Carlo runs"
    validate.write_outputs(spec, R, res)
    assert "WITHHELD" in (bass_project / "validation_report.md").read_text()
    assert not (bass_project / "mc_bands.csv").exists()


def test_heterogeneous_return_columns_in_one_chunk(bass_project):
    py = str(bass_project / "bass.py")
    a, b, full = validate.run_batch(py, [{"return_columns": ["Adopters"]},
                                         {"return_columns": ["adoption", "Adopters"]}, {}], workers=1)
    assert list(a.columns) == ["Adopters"]
    assert sorted(b.columns) == ["Adopters", "adoption"]
    assert np.allclose(a["Adopters"], full["Adopters"])
    assert np.allclose(b["adoption"], full["adoption"]) and np.allclose(b["Adopters"], full["Adopters"])


# ---------------------------------------------------------------- T4 error-ratio definitions (audit A2)
def test_euler_error_ratio_definitions(build):
    """Characterization. Euler: x_h = x + C h + O(h^2). Against the dt/4 run (what T4 reports):
    (x_dt - x_dt/4) / (x_dt/2 - x_dt/4) = (3/4)/(1/4) = 3. Against the exact solution: e(dt)/e(dt/2) = 2."""
    py = build("decay_ratio", DECAY, final_time=4, time_step=0.01)
    a, b, c = validate.run_batch(py, [{"time_step": dt, "saveper": 0.01} for dt in (0.01, 0.005, 0.0025)], workers=1)
    e1 = validate.dt_change(a, c, ["Level"])["Level"]
    e2 = validate.dt_change(b, c, ["Level"])["Level"]
    assert abs(e1 / e2 - 3) <= 0.1, e1 / e2
    exact = 100 * np.exp(-np.asarray(a.index, float))
    x1 = float(np.max(np.abs(np.asarray(a["Level"], float) - exact)))
    x2 = float(np.max(np.abs(np.asarray(b["Level"], float) - exact)))
    assert abs(x1 / x2 - 2) <= 0.1, x1 / x2


# ---------------------------------------------------------------- inspection IR-002, IR-004
@pytest.mark.parametrize("broken", ["[model\nname = ", SPEC.replace('mdl = "bass.mdl"\n', "")])
def test_main_invalidates_previous_release_when_spec_is_unreadable(bass_project, broken):
    import json
    d = bass_project
    (d / "validation_results.json").write_text(json.dumps({"all_pass": True}))   # an earlier successful release
    for f in validate.RELEASE_FILES:
        (d / f).write_text("stale")
    (d / "validation.toml").write_text(broken)
    assert validate.main([str(d / "validation.toml")]) == 1
    assert json.loads((d / "validation_results.json").read_text())["all_pass"] is False
    assert not any((d / f).exists() for f in validate.RELEASE_FILES)
    assert "WITHHELD" in (d / "validation_report.md").read_text()


def _nan_mc(monkeypatch, every):
    real = validate.run_batch

    def fake(py, runs, workers=None, **kw):
        out = real(py, runs, workers, **kw)
        if runs and runs[0].get("return_columns"):
            for i, df in enumerate(out):
                if df is not None and (every == 0 or i % every):
                    df.iloc[3, 0] = np.nan
        return out
    fake.last_errors = []
    monkeypatch.setattr(validate, "run_batch", fake)


@pytest.mark.parametrize("every,failed", [(0, 1000), (2, 500)])
def test_monte_carlo_non_finite_runs_count_as_failed_and_are_excluded(bass_project, monkeypatch, every, failed):
    (bass_project / "validation.toml").write_text(SPEC_NOPOL)
    _nan_mc(monkeypatch, every)
    _, R, res = validate.run_all(str(bass_project / "validation.toml"))
    t7 = R["tests"]["T7_monte_carlo"]
    assert t7["pass"] is False and t7["failed_runs"] == failed
    if failed == 1000:
        assert t7["detail"] == "no successful Monte Carlo runs" and res["bands"] == {}
    else:
        for b in res["bands"].values():
            assert all(np.all(np.isfinite(b[p])) for p in b)


# ---------------------------------------------------------------- inspection IR-006
DUP_GROUPS = ('[[conservation]]\nname = "population"\nstocks = ["Adopters"]\n\n'           # not conserved
              '[[conservation]]\nname = "population"\nstocks = ["Potential Adopters", "Adopters"]\n')


def test_group_drifts_keeps_same_named_groups_apart(bass_project):
    import pandas as pd
    df = pd.DataFrame({"A": [1.0, 2.0], "B": [1.0, 0.0]})
    groups = [{"name": "g", "stocks": ["A"]}, {"name": "g", "stocks": ["A", "B"]}]
    assert validate.group_drifts(df, groups) == [1.0, 0.0]
    assert validate.group_labels(groups) == ["g (#1)", "g (#2)"]
    assert validate.conservation_drift(df, groups) == 1.0


def test_same_named_conservation_group_cannot_hide_a_failing_one(bass_project):
    spec = SPEC_NOPOL.replace('[[conservation]]\nname = "population"\nstocks = ["Potential Adopters", "Adopters"]\n', DUP_GROUPS)
    assert spec.count('name = "population"') == 2
    (bass_project / "validation.toml").write_text(spec)
    _, R, _ = validate.run_all(str(bass_project / "validation.toml"))
    t6 = R["tests"]["T6_conservation"]
    assert t6["pass"] is False and not R["all_pass"]
    assert t6["max_rel_drift"]["base"] > 1e-6 and t6["max_rel_drift"]["monte_carlo_max"] > 1e-6
    assert any(p.startswith("group 'population (#1)'") and p.endswith("in base") for p in t6["problems"]), t6["problems"]
    assert any(p.startswith("group 'population (#1)'") and p.endswith("in monte_carlo_max") for p in t6["problems"])


# ---------------------------------------------------------------- inspection IR-007
def test_conservation_drift_survives_a_literal_name_that_looks_generated():
    import pandas as pd
    df = pd.DataFrame({"A": [1.0, 2.0], "B": [1.0, 0.0]})
    groups = [{"name": "g", "stocks": ["A"]}, {"name": "g", "stocks": ["A", "B"]},
              {"name": "g (#1)", "stocks": ["A", "B"]}]
    assert validate.conservation_drift(df, groups) == 1.0


def test_literal_generated_looking_name_cannot_hide_a_failing_group(bass_project):
    spec = SPEC_NOPOL.replace('[[conservation]]\nname = "population"\nstocks = ["Potential Adopters", "Adopters"]\n',
                              DUP_GROUPS + '\n[[conservation]]\nname = "population (#1)"\n'
                                           'stocks = ["Potential Adopters", "Adopters"]\n')
    (bass_project / "validation.toml").write_text(spec)
    _, R, _ = validate.run_all(str(bass_project / "validation.toml"))
    t6 = R["tests"]["T6_conservation"]
    assert t6["pass"] is False and not R["all_pass"]
    assert t6["max_rel_drift"]["base"] > 1e-6 and t6["max_rel_drift"]["monte_carlo_max"] > 1e-6


# ---------------------------------------------------------------- T5 peak rule (IR-003, strict reading)
def test_peak_tolerance_is_five_steps_of_the_reference_dt():
    """library/validation_tests.md T5: peak within 5 time steps of the reference run's OWN dt."""
    assert validate.peak_tolerance({"time_step": 0.01}, model_dt=0.25) == pytest.approx(0.05)
    assert validate.peak_tolerance({}, model_dt=0.0625) == pytest.approx(0.3125)    # no own dt: model dt


def test_T5_rejects_a_peak_tolerance_looser_than_the_rule(bass_project):
    spec_path = bass_project / "validation.toml"
    _, R, _ = validate.run_all(str(spec_path), n=999)                             # 0.25 <= 5 x 0.0625: allowed
    assert R["tests"]["T5_behavior"]["peak"]["pass"] is True
    spec_path.write_text(SPEC.replace("tolerance = 0.25", "tolerance = 1.0"))
    _, R, _ = validate.run_all(str(spec_path), n=999)
    pk = R["tests"]["T5_behavior"]["peak"]
    assert R["tests"]["T5_behavior"]["pass"] is False and pk["pass"] is False
    assert "peak tolerance 1 exceeds 5 x reference dt = 0.3125" in pk["error"]


def test_project_peak_tolerance_follows_the_rule():
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    spec = validate.load_spec(os.path.join(root, "projects", "bass-b2b-adoption", "validation.toml"))
    ref = spec["reference"]
    assert ref["peak"]["tolerance"] <= validate.peak_tolerance(ref, spec["model"]["time_step"]) + 1e-12


# [loop_check]: T8 reads link signs from base + these overrides when a parameter's base value (e.g. an optional
# effect defaulting to 0) freezes a link; dominance is still reported from the true base run.
_Q_OFF = SPEC.replace("base = 0.38\nlow = 0.3\n", "base = 0\nlow = 0\n")


def test_check_parameters_loop_check_rules():
    spec = validate.tomllib.loads(_Q_OFF + '\n[loop_check]\nset = { q = 0.38 }\n')
    assert validate.check_parameters(spec) == []
    spec = validate.tomllib.loads(_Q_OFF + '\n[loop_check]\nset = { r = 1 }\n')
    assert "loop_check: unknown parameter 'r'" in validate.check_parameters(spec)
    spec = validate.tomllib.loads(_Q_OFF + '\n[loop_check]\nset = { q = 0.9 }\n')
    assert "loop_check: q = 0.9 outside [low, high] = [0, 0.5]" in validate.check_parameters(spec)


def test_T8_fails_when_base_freezes_a_loop_link(bass_project):
    spec_path = bass_project / "validation.toml"
    spec_path.write_text(_Q_OFF)
    _, R, _ = validate.run_all(str(spec_path), n=999)
    t8 = R["tests"]["T8_loops"]
    assert t8["pass"] is False
    assert "'R word of mouth' declared R, detected undetermined" in t8["problems"]
    assert t8["polarity_run"] == "base"


def test_T8_loop_check_reads_polarity_from_override_run(bass_project):
    spec_path = bass_project / "validation.toml"
    spec_path.write_text(_Q_OFF + '\n[loop_check]\nset = { q = 0.38 }\n')
    spec, R, res = validate.run_all(str(spec_path), n=999)
    t8 = R["tests"]["T8_loops"]
    assert t8["pass"] is True, t8["problems"]
    assert t8["polarity_run"] == {"q": 0.38}
    pol = {x["name"]: x["polarity"] for x in t8["loops"]}
    assert pol["R word of mouth"] == "R" and pol["B saturation (word of mouth)"] == "B"
    # dominance comes from the true base run: with q = 0 the word-of-mouth loops never dominate
    wom = {x["id"] for x in t8["loops"] if "word of mouth" in x["name"]}
    assert t8["dominance"] and not any(p["loop"] in wom for p in t8["dominance"])
    validate.write_outputs(spec, R, res)
    assert "Loop polarity read from the base run with q = 0.38" in (bass_project / "validation_report.md").read_text()


def test_T8_loop_check_still_fails_a_wrong_declared_polarity(bass_project):
    """The override run only supplies link signs; it cannot make a wrongly declared loop pass."""
    spec_path = bass_project / "validation.toml"
    wrong = _Q_OFF.replace('name = "R word of mouth"\npolarity = "R"', 'name = "R word of mouth"\npolarity = "B"')
    assert wrong != _Q_OFF
    spec_path.write_text(wrong + '\n[loop_check]\nset = { q = 0.38 }\n')
    _, R, _ = validate.run_all(str(spec_path), n=999)
    t8 = R["tests"]["T8_loops"]
    assert t8["pass"] is False
    assert t8["problems"] == ["'R word of mouth' declared B, detected R"]
    assert t8["polarity_run"] == {"q": 0.38}


# T0 compares the committed .py with a fresh translation; PySD writes the keys of its dependency dictionaries
# (depends_on / other_deps) in an order that changes between processes, so only that order is normalized.
_DEPS = 'depends_on={"q": 1, "potential_adopters": 1, "adopter_fraction": 1}'


def _fixture_py(bass_project):
    text = (bass_project / "bass.py").read_text()
    assert text.count(_DEPS) == 1 and text.count("return 0.38") == 1
    return text


@pytest.mark.parametrize("old,new", [
    (_DEPS, 'depends_on={"adopter_fraction": 1, "q": 1, "potential_adopters": 1}'),        # reordered keys
])
def test_T0_dependency_key_order_is_normalized(bass_project, old, new):
    text = _fixture_py(bass_project)
    assert validate.same_translation(text, text.replace(old, new))


def test_T0_nested_other_deps_order_is_normalized(bass_project):
    """other_deps nests dependency dicts ("initial", "step"); their order is normalized too."""
    text = _fixture_py(bass_project)
    old = '            "initial": {"total_population": 1},\n            "step": {"adoption": 1},\n'
    new = '            "step": {"adoption": 1},\n            "initial": {"total_population": 1},\n'
    assert text.count(old) == 1
    assert validate.same_translation(text, text.replace(old, new))


@pytest.mark.parametrize("old,new,what", [
    ("return 0.38", "return 0.39", "changed coefficient"),
    (_DEPS, 'depends_on={"q": 1, "potential_adopters": 1, "adopter_fraction": 1, "p_1": 1}', "added dependency"),
    (_DEPS, 'depends_on={"q": 1, "potential_adopters": 1}', "removed dependency"),
    (_DEPS, 'depends_on={"q": 2, "potential_adopters": 1, "adopter_fraction": 1}', "changed dependency count"),
    ('    "initial_time": lambda: 0,\n    "final_time": lambda: 30,\n',
     '    "final_time": lambda: 30,\n    "initial_time": lambda: 0,\n', "reordered non-dependency dict"),
    ("CONTROL VARIABLES", "CONTROL VARS", "changed comment"),
])
def test_T0_detects_every_other_difference(bass_project, old, new, what):
    text = _fixture_py(bass_project)
    assert text.count(old) == 1, what
    assert validate.same_translation(text, text.replace(old, new)) is False, what


def test_T0_end_to_end_reordered_dependencies_pass_and_report_says_so(bass_project):
    py = bass_project / "bass.py"
    py.write_text(_fixture_py(bass_project).replace(_DEPS, 'depends_on={"adopter_fraction": 1, "q": 1, "potential_adopters": 1}'))
    spec, R, res = validate.run_all(str(bass_project / "validation.toml"), n=999)
    t0 = R["tests"]["T0_translation"]
    assert t0["pass"] is True and t0["comparison"] == "dependency-key order normalized"
    validate.write_outputs(spec, R, res)
    assert "dependency-key order normalized" in (bass_project / "validation_report.md").read_text()


# [loop_check] may decide only loops whose polarity cannot be read in the base run (a link that never changes there).
# A loop readable at base must match its declaration AT BASE, whatever the override run shows.
_Q_NEG = SPEC.replace("base = 0.38\nlow = 0.3\n", "base = -0.01\nlow = -0.01\n").replace("domain = [0, 5]", "domain = [-1, 5]")


def test_T8_override_cannot_rescue_a_declaration_wrong_at_base(bass_project):
    """Base q < 0 reverses the word-of-mouth loops; the standard declarations are wrong at base and right only
    under the override. T8 must fail."""
    assert _Q_NEG != SPEC
    spec_path = bass_project / "validation.toml"
    spec_path.write_text(_Q_NEG + '\n[loop_check]\nset = { q = 0.38 }\n')
    _, R, _ = validate.run_all(str(spec_path), n=999)
    assert R["tests"]["T1c_parameter_ranges"]["pass"] is True
    t8 = R["tests"]["T8_loops"]
    assert t8["pass"] is False
    assert "'R word of mouth' declared R, detected B" in t8["problems"]
    assert "'B saturation (word of mouth)' declared B, detected R" in t8["problems"]


def test_T8_override_cannot_break_a_declaration_right_at_base(bass_project):
    """The reverse: base polarities match the declarations; an override that would flip them is not consulted."""
    spec_path = bass_project / "validation.toml"
    spec_path.write_text(SPEC.replace("low = 0.3\n", "low = -0.01\n").replace("domain = [0, 5]", "domain = [-1, 5]")
                         + '\n[loop_check]\nset = { q = -0.01 }\n')
    _, R, _ = validate.run_all(str(spec_path), n=999)
    t8 = R["tests"]["T8_loops"]
    assert t8["pass"] is True, t8["problems"]
    assert t8["polarity_from_loop_check"] == []


def test_T8_declared_polarity_must_be_R_or_B_and_undetermined_loops_fail(bass_project):
    """Codex reproduction: q = 0 at base and in the override, both word-of-mouth loops declared "undetermined".
    String equality alone let that pass; T8 must reject the declarations and the unresolved loops."""
    spec_text = (_Q_OFF.replace('name = "R word of mouth"\npolarity = "R"', 'name = "R word of mouth"\npolarity = "undetermined"')
                 .replace('name = "B saturation (word of mouth)"\npolarity = "B"',
                          'name = "B saturation (word of mouth)"\npolarity = "undetermined"'))
    assert spec_text.count('polarity = "undetermined"') == 2
    spec_path = bass_project / "validation.toml"
    spec_path.write_text(spec_text + '\n[loop_check]\nset = { q = 0 }\n')
    _, R, _ = validate.run_all(str(spec_path), n=999)
    assert R["tests"]["T1c_parameter_ranges"]["pass"] is True
    t8 = R["tests"]["T8_loops"]
    assert t8["pass"] is False
    for name in ("R word of mouth", "B saturation (word of mouth)"):
        assert f"'{name}' declared polarity 'undetermined': must be R or B" in t8["problems"]
        assert f"'{name}' polarity still undetermined after the [loop_check] override" in t8["problems"]


def test_T8_undetermined_loop_fails_without_loop_check(bass_project):
    """Without [loop_check] an undetermined loop gets the same explicit message (base run)."""
    spec_path = bass_project / "validation.toml"
    spec_path.write_text(_Q_OFF)
    _, R, _ = validate.run_all(str(spec_path), n=999)
    assert "'R word of mouth' polarity undetermined in the base run (no [loop_check])" in R["tests"]["T8_loops"]["problems"]


# ---------------------------------------------------------------- T8 empty loop-strength view
# With both adoption routes off nothing in the model ever moves, so every link score is 0, every loop score is 0,
# and every relative score is NaN: the explorer's loop-strength chart would have nothing to draw. Found on
# projects/car-dealership-profit, whose base case freezes a link in all 67 of its loops.
_FROZEN = _Q_OFF.replace("base = 0.03\nlow = 0.01\n", "base = 0\nlow = 0\n")
# the analytic Bass reference divides by p, so the limit case goes with the dynamics it was checking
_ALL_OFF = _FROZEN[:_FROZEN.index("\n[reference]")] + _FROZEN[_FROZEN.index("\n[sectors]"):]
_WHY = 'dominance_empty_at_base = "both adoption routes are off in the base case"\n'


def _scored_steps(build, name, eqs):
    py = build(name, eqs)
    df = validate.run_batch(py, [{"saveper_dt": True}])[0]
    m = ld.parse_model(py)
    return ld.analyze(m, ld.values_from_frame(m, df))


def test_analyze_counts_the_steps_that_carry_a_loop_score(build):
    """loop_detector says how many time steps have a non-zero loop score, which is what tells an empty
    loop-strength view from a populated one."""
    live = _scored_steps(build, "live", BASS)
    assert live["n_steps"] > 0
    assert live["scored_steps"] == live["n_steps"]

    # the same structure with both adoption rates at zero: nothing moves, so no step carries a score
    frozen_eqs = [(e.replace("p = 0.03", "p = 0").replace("q = 0.38", "q = 0"), u) for e, u in BASS]
    frozen = _scored_steps(build, "frozen", frozen_eqs)
    assert frozen["n_steps"] > 0
    assert frozen["scored_steps"] == 0
    assert all(d["mean_abs_relative_score"] is None for d in frozen["loops"])


def test_T8_fails_when_no_loop_scores_at_base(bass_project):
    spec_path = bass_project / "validation.toml"
    spec_path.write_text(_ALL_OFF)
    _, R, _ = validate.run_all(str(spec_path), n=999)
    t8 = R["tests"]["T8_loops"]
    assert t8["scored_steps"] == 0 and t8["n_steps"] > 0
    assert any("loop-strength view of every page built from this model is empty" in p for p in t8["problems"]), t8["problems"]
    assert t8["pass"] is False


def test_T8_accepts_an_empty_loop_strength_view_when_the_reason_is_declared(bass_project):
    spec_path = bass_project / "validation.toml"
    spec_path.write_text(_WHY + _ALL_OFF)
    _, R, _ = validate.run_all(str(spec_path), n=999)
    t8 = R["tests"]["T8_loops"]
    assert t8["scored_steps"] == 0
    assert not any("loop-strength view" in p for p in t8["problems"]), t8["problems"]
    assert t8["dominance_empty_at_base"] == "both adoption routes are off in the base case"


def test_T8_rejects_a_declaration_that_is_not_needed(bass_project):
    """A stale declaration would quietly excuse a future empty view, so it has to go when the view is not empty."""
    spec_path = bass_project / "validation.toml"
    spec_path.write_text(_WHY + SPEC)
    _, R, _ = validate.run_all(str(spec_path), n=999)
    t8 = R["tests"]["T8_loops"]
    assert t8["scored_steps"] > 0
    assert any("remove the declaration" in p for p in t8["problems"]), t8["problems"]
    assert t8["pass"] is False


def test_T8_rejects_a_dominance_declaration_that_is_not_a_reason(bass_project):
    spec_path = bass_project / "validation.toml"
    spec_path.write_text("dominance_empty_at_base = true\n" + _ALL_OFF)
    _, R, _ = validate.run_all(str(spec_path), n=999)
    t8 = R["tests"]["T8_loops"]
    assert any("must be a non-empty string" in p for p in t8["problems"]), t8["problems"]


@pytest.mark.parametrize("units", ["Widgets*", "1/", "Month^", "(Firm", "Firm*/Month"])
def test_a_truncated_unit_is_a_unit_problem_not_a_crash(units):
    """These used to raise IndexError out of parse_units, which check_units does not catch: one T1 problem became a
    fatal with an empty test table."""
    with pytest.raises(validate.UnitError):
        validate.parse_units(units)


def test_failed_T0_refuses_to_run_the_model_at_all(bass_project):
    """Every run imports (executes) the committed .py. When T0 says it is not a fresh translation of the .mdl, it must
    not be run: reporting the mismatch afterwards is too late."""
    py = bass_project / "bass.py"
    py.write_text(py.read_text().replace("return 0.38", "return 0.39"))
    spec, R, res = validate.run_all(str(bass_project / "validation.toml"))
    assert R["tests"]["T0_translation"]["pass"] is False
    assert R["all_pass"] is False and res is None
    assert "no model runs performed" in R["fatal"]
    assert not any(k.startswith(("T3", "T4", "T5", "T6", "T7")) for k in R["tests"])     # nothing was run
    assert "T1_units" in R["tests"]                                                      # the ast-only tests still ran


@pytest.mark.parametrize("value", ["/etc/passwd", "../outside.py", "model/../../outside.py"])
def test_a_spec_cannot_point_the_model_outside_its_project(bass_project, value):
    toml = bass_project / "validation.toml"
    toml.write_text(toml.read_text().replace('py = "bass.py"', f'py = "{value}"'))
    with pytest.raises(ValueError, match="must be inside the project folder"):
        validate.load_spec(str(toml))


def test_a_symlinked_model_file_pointing_out_of_the_project_is_refused(bass_project, tmp_path):
    outside = tmp_path / "outside.py"
    outside.write_text("")
    (bass_project / "linked.py").symlink_to(outside)
    toml = bass_project / "validation.toml"
    toml.write_text(toml.read_text().replace('py = "bass.py"', 'py = "linked.py"'))
    with pytest.raises(ValueError, match="must be inside the project folder"):
        validate.load_spec(str(toml))


def test_the_ordinary_relative_model_paths_are_unchanged(bass_project):
    spec = validate.load_spec(str(bass_project / "validation.toml"))
    assert spec["model"]["py_path"] == str(bass_project / "bass.py")
    assert spec["model"]["mdl_path"] == str(bass_project / "bass.mdl")
    assert sorted(validate.model_hashes(spec)) == ["bass.mdl", "bass.py"]
