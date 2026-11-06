"""validate.py must FAIL, with a specific message, on deliberately broken models, and must withhold results.

Each broken model is a minimal edit of the Bass fixture. run_all(n=999) skips the Monte Carlo runs, so
these tests assert only the TARGETED test's flag and message; the unbroken control under the same call
shows that test passing. Withholding is proved separately with T7 passing (N = 1000).
"""
import copy
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

import validate
from conftest import BASS, SPEC, make_project

RELEASE = validate.RELEASE_FILES
GATING = ["T0_translation", "T1_units", "T1b_mece", "T1c_parameter_ranges", "T3_extremes", "T4_dt_halving",
          "T5_behavior", "T6_conservation", "T7_monte_carlo", "T8_loops"]
ENGINE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _edit(eqs, name, new_def, units=None):
    out = []
    for d, u in eqs:
        if d.split("=")[0].strip() == name:
            out.append((new_def, units or u))
        else:
            out.append((d, u))
    return out


def _run(tmp_path, name, eqs, spec_text=SPEC, time_step=0.0625):
    d = make_project(tmp_path / name, eqs, spec_text, final_time=30, time_step=time_step)
    return validate.run_all(str(d / "validation.toml"), n=999)[1]["tests"]


@pytest.fixture(scope="module")
def control(tmp_path_factory):
    d = make_project(tmp_path_factory.mktemp("control") / "proj", BASS, SPEC, final_time=30, time_step=0.0625)
    return validate.run_all(str(d / "validation.toml"), n=999)[1]["tests"]


def test_unit_mismatch_fails_T1(tmp_path, control):
    assert control["T1_units"]["pass"]
    T = _run(tmp_path, "units", _edit(BASS, "total population", "total population = 1000", "Firm"))
    assert T["T1_units"]["pass"] is False
    assert "adopter fraction: equation vs declared: Person/Firm vs Dmnl" in T["T1_units"]["problems"]


def test_leaking_stock_fails_T6(tmp_path, control):
    assert control["T6_conservation"]["pass"]
    eqs = _edit(BASS, "Adopters", "Adopters = INTEG(adoption * arrival fraction, 0)") + [("arrival fraction = 0.99", "Dmnl")]
    spec = SPEC.replace('market = ["Potential Adopters",', 'market = ["arrival fraction", "Potential Adopters",')
    T = _run(tmp_path, "leak", eqs, spec)
    t6 = T["T6_conservation"]
    assert t6["pass"] is False and t6["max_rel_drift"]["base"] > 1e-6
    assert any(re.fullmatch(r"group 'population': max relative drift \S+ > 1e-06 in base", p) for p in t6["problems"]), t6["problems"]


def test_wrong_loop_polarity_fails_T8(tmp_path, control):
    assert control["T8_loops"]["pass"]
    eqs = _edit(BASS, "adopter fraction", "adopter fraction = 1 - Adopters / total population")
    T = _run(tmp_path, "polarity", eqs)
    assert T["T8_loops"]["pass"] is False
    assert "'R word of mouth' declared R, detected B" in T["T8_loops"]["problems"]


def test_dt_unstable_fails_T4(tmp_path, control):
    assert control["T4_dt_halving"]["pass"]
    T = _run(tmp_path, "dt", BASS, SPEC.replace("time_step = 0.0625", "time_step = 1"), time_step=1)
    t4 = T["T4_dt_halving"]
    assert t4["pass"] is False and t4["max_rel_change"] > 0.01
    pat = r"Adopters \(base\): max relative change \S+ between dt=1 and dt/2 exceeds 0.01"
    assert any(re.fullmatch(pat, p) for p in t4["problems"]), t4["problems"]


# ---------------------------------------------------------------- withholding, with T7 passing
@pytest.fixture(scope="module")
def passing(tmp_path_factory):
    d = make_project(tmp_path_factory.mktemp("pass") / "proj", BASS, SPEC, final_time=30, time_step=0.0625)
    spec, R, res = validate.run_all(str(d / "validation.toml"))
    assert R["all_pass"], {k: v for k, v in R["tests"].items() if not v["pass"]}
    released = copy.deepcopy(R)
    validate.write_outputs(spec, released, res)
    assert all((d / f).exists() for f in RELEASE)
    return spec, R, res, d


def _write_to(tmp_path, spec, R, res):
    spec = copy.deepcopy(spec)
    spec["_dir"] = str(tmp_path)
    validate.write_outputs(spec, R, res)
    return (tmp_path / "validation_report.md").read_text()


@pytest.mark.parametrize("name", GATING)
def test_each_gating_failure_withholds_results(passing, tmp_path, name):
    spec, R, res, _ = passing
    assert name in R["tests"]
    R = copy.deepcopy(R)
    R["tests"][name]["pass"] = False
    R["all_pass"] = all(t["pass"] for t in R["tests"].values() if t.get("gating", True))
    assert R["all_pass"] is False
    report = _write_to(tmp_path, spec, R, res)
    assert "WITHHELD" in report
    assert not any((tmp_path / f).exists() for f in RELEASE)


def test_non_gating_policy_ranking_still_releases(passing, tmp_path):
    spec, R, res, _ = passing
    R = copy.deepcopy(R)
    R["tests"]["T7b_policy_ranking"]["pass"] = False
    R["all_pass"] = all(t["pass"] for t in R["tests"].values() if t.get("gating", True))
    report = _write_to(tmp_path, spec, R, res)
    assert R["all_pass"] and "WITHHELD" not in report and (tmp_path / "mc_bands.csv").exists()


def test_failed_rerun_removes_previously_released_results(passing, tmp_path):
    _, _, _, d = passing
    work = tmp_path / "proj"
    shutil.copytree(d, work)
    assert all((work / f).exists() for f in RELEASE)
    (work / "validation.toml").write_text(SPEC.replace('polarity = "R"', 'polarity = "B"'))
    spec, R, res = validate.run_all(str(work / "validation.toml"), n=999)
    validate.write_outputs(spec, R, res)
    assert not any((work / f).exists() for f in RELEASE)
    assert "WITHHELD" in (work / "validation_report.md").read_text()


def _fan_chart(csv_path, out):
    return subprocess.run([sys.executable, "-I", os.path.join(ENGINE, "fan_chart.py"), str(csv_path), str(out),
                           "Adopters:Adopters"], capture_output=True, text=True)


@pytest.mark.parametrize("results", [None, {"all_pass": False}])
def test_fan_chart_refuses_unvalidated_bands(passing, tmp_path, results):
    _, _, _, d = passing
    shutil.copy(d / "mc_bands.csv", tmp_path / "mc_bands.csv")
    if results is not None:
        (tmp_path / "validation_results.json").write_text(json.dumps(results))
    p = _fan_chart(tmp_path / "mc_bands.csv", tmp_path / "fan.png")
    assert p.returncode != 0 and "validation has not passed" in (p.stderr + p.stdout)
    assert not (tmp_path / "fan.png").exists()


def test_fan_chart_draws_validated_bands(passing, tmp_path):
    _, _, _, d = passing
    p = _fan_chart(d / "mc_bands.csv", tmp_path / "fan.png")
    assert p.returncode == 0, p.stderr
    assert (tmp_path / "fan.png").exists()


def test_fan_chart_labels_come_from_the_model_not_from_a_launch_example(passing, tmp_path):
    """The x label used to say 'Months since launch' for every model, and 0.73 was printed as 1."""
    sys.path.insert(0, ENGINE)
    import fan_chart
    _, _, _, d = passing
    assert fan_chart.time_label(str(d / "mc_bands.csv")).startswith("Time (")
    assert fan_chart.time_label(str(tmp_path / "mc_bands.csv")) == "Time"
    assert fan_chart.number(0.73) == "0.73" and fan_chart.number(0.0248) == "0.0248"
    assert fan_chart.number(12345.6) == "12,346" and fan_chart.number(0) == "0"


def test_successful_rerun_without_policies_removes_old_policy_results(passing, tmp_path):
    """Inspection IR-005: a release must contain only files the current run produced."""
    _, _, _, d = passing
    work = tmp_path / "proj"
    shutil.copytree(d, work)
    assert (work / "policy_results.csv").exists()
    (work / "validation.toml").write_text(SPEC.split("\n[policy]")[0] + "\n")
    spec, R, res = validate.run_all(str(work / "validation.toml"))
    assert R["all_pass"], {k: v for k, v in R["tests"].items() if not v["pass"]}
    validate.write_outputs(spec, R, res)
    assert (work / "mc_bands.csv").exists() and (work / "loop_dominance.json").exists()
    assert not (work / "policy_results.csv").exists()
    assert "WITHHELD" not in (work / "validation_report.md").read_text()
