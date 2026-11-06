"""Regression tests for the third read-only review of PR #3 (at 2a09ae9). Each failed before its class fix.

Class A: one completeness rule for result frames (validate.frame_problem), used by T3, Monte Carlo, parity and the
loop-score gate. A frame must have exactly the expected time grid and every expected column; the expectation comes
from the model file and the spec, never from the frame. Empty frames fail.
Class B: required records fail closed. A record that is missing, empty, unparseable or truncated is an error in the
release gate, check_repo and the stamp. Required file lists come from checks.py and the generator's declarations.
Finding 1 is tested as a claim: a stale passing record left by an interrupted or invalid-argument run cannot release
a changed model, spec or checks."""
import json
import os
import shutil
import subprocess
import sys

import numpy as np
import pytest

import build_explorer as be
import explorer_ltm as el
import explorer_parity as ep
import explorer_release as er
import export_js
import loop_detector as ld
import validate

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASS = os.path.join(ROOT, "projects", "bass-b2b-adoption")
SAAS = os.path.join(ROOT, "projects", "saas-churn-vs-winrate")


def _copy(src, tmp_path, keep_page=False, parent=None):
    d = (parent or tmp_path) / os.path.basename(src)
    shutil.copytree(src, d, ignore=None if keep_page else shutil.ignore_patterns("explorer.html", "explorer_parity.json"))
    return str(d)


def _bump(path):
    lines = open(path).read().splitlines()
    cells = lines[1].split(",")
    cells[1] = repr(float(cells[1]) * 10 + 1)
    lines[1] = ",".join(cells)
    open(path, "w").write("\n".join(lines) + "\n")


def _check_repo(root):
    return subprocess.run([sys.executable, "-I", os.path.join(ROOT, "engine", "check_repo.py"), "--projects-root", str(root)],
                          cwd=ROOT, capture_output=True, text=True)


# ---------------------------------------------------------------- class A: the shared completeness rule
@pytest.fixture(scope="module")
def bass():
    spec = validate.load_spec(os.path.join(BASS, "validation.toml"))
    py = spec["model"]["py_path"]
    df = validate.run_batch(py, [{"params": validate.base_params(spec)}])[0]
    return spec, py, df


def test_a_expected_grid_and_columns_come_from_the_model(bass):
    spec, py, df = bass
    ctl = validate.model_controls(py)
    grid = validate.expected_times(ctl["initial_time"], ctl["final_time"], ctl["saveper"], ctl["time_step"])
    assert np.allclose(np.asarray(df.index, float), grid) and len(grid) == len(df)
    assert set(validate.model_columns(py)) == set(df.columns)


@pytest.mark.parametrize("cut", ["healthy", "empty", "first-row", "endpoints", "missing-column", "shifted-grid"])
def test_a_frame_problem(bass, cut):
    spec, py, df = bass
    ctl = validate.model_controls(py)
    grid = validate.expected_times(ctl["initial_time"], ctl["final_time"], ctl["saveper"], ctl["time_step"])
    cols = validate.model_columns(py)
    f = {"healthy": df, "empty": df.iloc[:0], "first-row": df.iloc[:1], "endpoints": df.iloc[[0, -1]],
         "missing-column": df.drop(columns=["Customers"]), "shifted-grid": df.set_axis(df.index + 0.5)}[cut]
    p = validate.frame_problem(f, grid, cols)
    assert (p is None) == (cut == "healthy"), p


def _cases():
    return json.load(open(os.path.join(BASS, "validation_results.json")))["tests"]["T3_extremes"]["cases"]


@pytest.mark.parametrize("cut", ["empty", "truncated", "missing-column"])
def test_f5_t3_fails_on_an_incomplete_extreme_frame(monkeypatch, cut):
    real = validate.run_batch
    calls = {"n": 0}
    n_cases = _cases()

    def hook(py, runs, *a, **k):
        calls["n"] += 1
        out = real(py, runs, *a, **k)
        if calls["n"] == 1:
            i = len(out) - n_cases                 # the first extreme case: a parameter sweep with no expectation
            out[i] = {"empty": out[i].iloc[:0], "truncated": out[i].iloc[:-1],
                      "missing-column": out[i].drop(columns=["Customers"])}[cut]
        return out
    monkeypatch.setattr(validate, "run_batch", hook)
    _, R, _ = validate.run_all(os.path.join(BASS, "validation.toml"))
    t3 = R["tests"]["T3_extremes"]
    assert t3["pass"] is False and any("incomplete run" in f for f in t3["failures"]), t3["failures"][:3]


@pytest.mark.parametrize("cut", ["first-row", "missing-column", "empty"])
def test_f6_monte_carlo_counts_incomplete_runs_as_failed(monkeypatch, cut):
    real = validate.run_batch

    def hook(py, runs, *a, **k):
        out = real(py, runs, *a, **k)
        if any(r.get("return_columns") for r in runs):
            out = [None if df is None else {"first-row": df.iloc[:1], "missing-column": df.iloc[:, 1:],
                                            "empty": df.iloc[:0]}[cut] for df in out]
        return out
    monkeypatch.setattr(validate, "run_batch", hook)
    _, R, _ = validate.run_all(os.path.join(BASS, "validation.toml"))
    t7 = R["tests"]["T7_monte_carlo"]
    assert t7["pass"] is False and t7["failed_runs"] > 0 and R["all_pass"] is False


def test_f7_parity_fails_on_endpoint_and_stock_only_frames(monkeypatch):
    spec = validate.load_spec(os.path.join(BASS, "validation.toml"))
    stocks = [c.name for c in ld.parse_model(spec["model"]["py_path"]).stocks]
    eng = export_js.emit_js(export_js.load_ir(spec["model"]["py_path"]))
    real, on = validate.run_batch, ep.node_run
    monkeypatch.setattr(ep.validate, "run_batch", lambda *a, **k: [None if df is None else df.iloc[[0, -1]][stocks] for df in real(*a, **k)])

    def js_cut(*a, **k):
        out = on(*a, **k)
        for r in out:
            r["time"] = [r["time"][0], r["time"][-1]]
            r["series"] = {c: [r["series"][c][0], r["series"][c][-1]] for c in stocks}
        return out
    monkeypatch.setattr(ep, "node_run", js_cut)
    rep = ep.run_parity(spec, eng, n_random=1)
    assert rep["pass"] is False and any("incomplete" in e["error"] for e in rep["errors"]), rep["errors"][:2]


def test_f7_loop_score_gate_fails_on_truncated_pysd_frames(monkeypatch):
    spec = validate.load_spec(os.path.join(BASS, "validation.toml"))
    real = validate.run_batch
    monkeypatch.setattr(el.validate, "run_batch", lambda *a, **k: [None if df is None else df.iloc[::2] for df in real(*a, **k)])
    g = el.run_ltm_gate(spec, BASS)
    assert g["pass"] is False and g["mode"] == "precomputed", g


# ---------------------------------------------------------------- class B: required records fail closed
def test_f2_deleting_the_generator_record_is_refused(tmp_path):
    d = _copy(SAAS, tmp_path)
    os.remove(os.path.join(d, "gate8_results.json"))
    _bump(os.path.join(d, "scenario_bands.csv"))
    with pytest.raises(er.Refused, match="gate8_results.json is missing"):
        be.build(d)


@pytest.mark.parametrize("content", ["", "{not json", "{}"])
def test_b_empty_or_unparseable_generator_record_is_refused(tmp_path, content):
    d = _copy(SAAS, tmp_path)
    open(os.path.join(d, "gate8_results.json"), "w").write(content)
    with pytest.raises(er.Refused, match="gate8_results.json"):
        er.check_release(d)


def test_b_generator_requirements_come_from_the_script(tmp_path):
    """WRITES and READS are declared in gate8_analysis.py; dropping a declared output from the record is refused."""
    want_out, want_in = er.generator_declaration(os.path.join(SAAS, "gate8_analysis.py"))
    assert "scenario_bands.csv" in want_out and {"policy_results.csv", "loop_dominance.json"} <= want_in
    d = _copy(SAAS, tmp_path)
    p = os.path.join(d, "gate8_results.json")
    r = json.load(open(p))
    r["output_files"].pop("scenario_bands.csv")
    json.dump(r, open(p, "w"))
    with pytest.raises(er.Refused, match="does not record the sha256 of scenario_bands.csv"):
        er.check_release(d)


def test_f3_a_truncated_external_record_is_refused(tmp_path):
    d = _copy(SAAS, tmp_path)
    p = os.path.join(d, "checks_results.json")
    r = json.load(open(p))
    r["external_inputs"].pop("projects/bass-b2b-adoption/model/bass_b2b_adoption.py")
    json.dump(r, open(p, "w"))
    with pytest.raises(er.Refused, match="no sha256 for projects/bass-b2b-adoption/model/bass_b2b_adoption.py"):
        er.check_release(d)


def test_f3_required_external_files_come_from_checks_py_and_the_other_spec():
    req = er.required_external_inputs(SAAS)
    assert req == {"projects/bass-b2b-adoption/validation.toml", "projects/bass-b2b-adoption/model/bass_b2b_adoption.mdl",
                   "projects/bass-b2b-adoption/model/bass_b2b_adoption.py"}


@pytest.mark.parametrize("rec", ["validation_results.json", "checks_results.json"])
@pytest.mark.parametrize("content", ["", "{not json"])
def test_f4_check_repo_fails_on_an_empty_or_unparseable_record(tmp_path, rec, content):
    root = tmp_path / "projects"
    root.mkdir()
    d = _copy(SAAS, tmp_path, parent=root)
    open(os.path.join(d, rec), "w").write(content)
    p = _check_repo(root)
    assert p.returncode == 1 and rec in p.stdout, p.stdout


def test_b_stamp_fails_on_an_unreadable_record(tmp_path):
    d = _copy(SAAS, tmp_path, keep_page=True)
    open(os.path.join(d, "gate8_results.json"), "w").write("")
    assert any("gate8_results.json" in e for e in er.shipped_errors(d))


# ---------------------------------------------------------------- finding 1: a stale passing record is not a release
def _change(d, what):
    if what == "model":
        open(os.path.join(d, "model", os.path.basename(d).replace("-", "_") + ".py"), "a").write("\n# changed\n")
    elif what == "spec":
        open(os.path.join(d, "validation.toml"), "a").write("\n# changed\n")
    else:
        open(os.path.join(d, "checks.py"), "a").write("\n# changed\n")


@pytest.mark.parametrize("exit_path", ["invalid-arguments", "interrupt-before-writing", "interrupt-after-outputs"])
@pytest.mark.parametrize("what", ["model", "spec", "checks"])
def test_f1_a_stale_passing_record_cannot_release_a_change(tmp_path, monkeypatch, exit_path, what):
    d = _copy(SAAS, tmp_path)
    before = open(os.path.join(d, "validation_results.json")).read()
    er.check_release(d)                                   # the unchanged project is released
    _change(d, what)
    spec_path = os.path.join(d, "validation.toml")
    if exit_path == "invalid-arguments":
        with pytest.raises(SystemExit):
            validate.main([spec_path, "--n", "not-a-number"])
    elif exit_path == "interrupt-before-writing":
        def stop(*a, **k):
            raise KeyboardInterrupt
        monkeypatch.setattr(validate, "run_all", stop)
        with pytest.raises(KeyboardInterrupt):
            validate.main([spec_path])
    else:                                                 # result files rewritten, interrupted before the record
        real_dump = validate.json.dump

        class J:
            def __getattr__(self, k):
                return getattr(json, k)

            @staticmethod
            def dump(obj, fp, *a, **k):
                if getattr(fp, "name", "").endswith("validation_results.json"):
                    raise KeyboardInterrupt
                return real_dump(obj, fp, *a, **k)
        monkeypatch.setattr(validate, "json", J())
        with pytest.raises(KeyboardInterrupt):
            validate.main([spec_path])
    now = open(os.path.join(d, "validation_results.json")).read()
    if exit_path == "interrupt-after-outputs":
        # open(..., "w") empties the record before the interrupted dump: it is not a stale pass but an unreadable one
        assert now == ""
        with pytest.raises(er.Refused, match="unreadable"):
            er.check_release(d)
    else:
        assert now == before                              # the stale passing record is still there ...
        with pytest.raises(er.Refused, match="changed after"):   # ... and cannot release the changed project
            er.check_release(d)
