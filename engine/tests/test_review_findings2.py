"""Regression tests for the second read-only review of PR #3 (at 556bb59) and the fail-open audit that followed.
Each test failed before its fix. Finding 4 (baseline "base values") is in test_explorer_intake.py.

The audit's rule: a gate fails unless the items it is meant to compare are all present and non-empty, with the
expected set derived from the model, the spec or the code that produced the record, never typed here."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

import build_explorer as be
import contrast_check as cc
import explorer_ltm as el
import explorer_parity as ep
import explorer_release as er
import export_js
import validate

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASS = os.path.join(ROOT, "projects", "bass-b2b-adoption")
SAAS = os.path.join(ROOT, "projects", "saas-churn-vs-winrate")


def _copy(src, tmp_path, keep_page=False, parent=None):
    d = (parent or tmp_path) / os.path.basename(src)
    shutil.copytree(src, d, ignore=None if keep_page else shutil.ignore_patterns("explorer.html", "explorer_parity.json"))
    return str(d)


def _edit_json(path, fn):
    r = json.load(open(path))
    fn(r)
    json.dump(r, open(path, "w"))


def _bump_cell(path):
    """Change one numeric cell of a CSV (first data row, second column), keeping the file well formed."""
    lines = open(path).read().splitlines()
    cells = lines[1].split(",")
    cells[1] = repr(float(cells[1]) * 10 + 1)
    lines[1] = ",".join(cells)
    open(path, "w").write("\n".join(lines) + "\n")


# ---- finding 1: validation outputs bound to the run that wrote them
def test_f1_edited_validation_output_is_refused(tmp_path):
    d = _copy(BASS, tmp_path)
    _bump_cell(os.path.join(d, "mc_bands.csv"))
    with pytest.raises(er.Refused, match="mc_bands.csv changed after validation"):
        be.build(d)


def test_f1_results_without_output_hashes_are_refused(tmp_path):
    d = _copy(BASS, tmp_path)
    _edit_json(os.path.join(d, "validation_results.json"), lambda r: r.pop("output_files", None))
    with pytest.raises(er.Refused, match="does not record the sha256 of the result files"):
        er.check_release(d)


@pytest.mark.parametrize("project", [BASS, SAAS], ids=["bass", "saas"])
def test_f1_a_truncated_output_record_is_refused(tmp_path, project):
    """The expected result files are derived from the spec (policies -> policy_results.csv, loops ->
    loop_dominance.json), so dropping one from the record cannot pass."""
    d = _copy(project, tmp_path)
    _edit_json(os.path.join(d, "validation_results.json"), lambda r: r["output_files"].pop("loop_dominance.json"))
    with pytest.raises(er.Refused, match="does not record the sha256 of loop_dominance.json"):
        er.check_release(d)


def test_f1_edited_gate8_output_is_refused(tmp_path):
    d = _copy(SAAS, tmp_path)
    _bump_cell(os.path.join(d, "scenario_bands.csv"))
    with pytest.raises(er.Refused, match="scenario_bands.csv changed after gate8_analysis.py ran"):
        er.check_release(d)


@pytest.mark.parametrize("key", ["loop_dominance.json", "policy_results.csv", "gate8_analysis.py"])
def test_f1_gate8_run_on_other_inputs_is_refused(tmp_path, key):
    d = _copy(SAAS, tmp_path)
    _edit_json(os.path.join(d, "gate8_results.json"), lambda r: r["inputs"].__setitem__(key, "0" * 64))
    with pytest.raises(er.Refused, match=f"{key} changed after gate8_analysis.py ran"):
        er.check_release(d)


def test_f1_edited_delay_audit_is_refused(tmp_path):
    d = _copy(BASS, tmp_path)
    _edit_json(os.path.join(d, "delay_audit.json"), lambda r: r.__setitem__("delays", []))
    with pytest.raises(er.Refused, match="delay_audit.json does not match the delay audit of the current model"):
        er.check_release(d)


# ---- finding 2: required records may not be truncated to empty defaults
def test_f2_missing_external_inputs_is_refused(tmp_path):
    d = _copy(SAAS, tmp_path)
    _edit_json(os.path.join(d, "checks_results.json"), lambda r: r.pop("external_inputs"))
    with pytest.raises(er.Refused, match="checks_results.json does not record the sha256 of the files it checked"):
        er.check_release(d)


def test_f2_emptied_external_inputs_is_refused(tmp_path):
    """checks.py reads bass-b2b-adoption (found in its source), so an empty external record cannot pass."""
    d = _copy(SAAS, tmp_path)
    _edit_json(os.path.join(d, "checks_results.json"), lambda r: r.__setitem__("external_inputs", {}))
    with pytest.raises(er.Refused, match="no sha256 for projects/bass-b2b-adoption/"):
        er.check_release(d)


# ---- finding 3: check_repo checks every project, page or not
def _check_repo(root):
    return subprocess.run([sys.executable, "-I", os.path.join(ROOT, "engine", "check_repo.py"), "--projects-root", str(root)],
                          cwd=ROOT, capture_output=True, text=True)


def test_f3_stale_checks_are_found_without_a_page(tmp_path):
    root = tmp_path / "projects"
    root.mkdir()
    d = _copy(SAAS, tmp_path, parent=root)
    open(os.path.join(d, "checks.py"), "a").write("\n# edited\n")
    p = _check_repo(root)
    assert p.returncode == 1 and "checks.py changed after the project checks ran" in p.stdout, p.stdout


def test_f3_edited_outputs_are_found_without_a_page(tmp_path):
    root = tmp_path / "projects"
    root.mkdir()
    d = _copy(BASS, tmp_path, parent=root)
    _bump_cell(os.path.join(d, "mc_bands.csv"))
    p = _check_repo(root)
    assert p.returncode == 1 and "mc_bands.csv changed after validation" in p.stdout, p.stdout


def test_f3_unedited_projects_without_pages_pass(tmp_path):
    root = tmp_path / "projects"
    root.mkdir()
    _copy(BASS, tmp_path, parent=root)
    _copy(SAAS, tmp_path, parent=root)
    p = _check_repo(root)
    assert p.returncode == 0 and "explorers=0" in p.stdout, p.stdout


# ---- finding 5: empty series are not comparisons
@pytest.fixture(scope="module")
def bass_spec_engine():
    spec = validate.load_spec(os.path.join(BASS, "validation.toml"))
    return spec, export_js.emit_js(export_js.load_ir(spec["model"]["py_path"]))


def test_f5_parity_metrics_on_empty_series_is_infinite():
    assert ep.parity_metrics([], [])["scale"] == float("inf")
    assert ep.parity_metrics([1.0], [])["scale"] == float("inf")


def test_f5_parity_fails_on_empty_frames(bass_spec_engine, monkeypatch):
    spec, eng = bass_spec_engine
    n = len(ep.lever_settings(spec, ep.N_RANDOM, ep.SEED))
    monkeypatch.setattr(ep.validate, "run_batch", lambda *a, **k: [pd.DataFrame() for _ in range(n)])
    monkeypatch.setattr(ep, "node_run", lambda *a, **k: [{"time": [], "series": {}} for _ in range(n)])
    rep = ep.run_parity(spec, eng)
    assert rep["pass"] is False and rep["errors"], rep


@pytest.mark.parametrize("cut", ["drop-stock", "short-grid"])
def test_f5_parity_fails_on_truncated_frames(bass_spec_engine, monkeypatch, cut):
    """Each PySD run must hold every model stock on the full time grid (both derived from the model and the spec)."""
    spec, eng = bass_spec_engine
    orig = validate.run_batch

    def trunc(*a, **k):
        out = orig(*a, **k)
        if cut == "drop-stock":
            return [df.drop(columns=["Customers"]) for df in out]
        return [df.iloc[:-1] for df in out]
    orig_node = ep.node_run

    def trunc_js(*a, **k):
        out = orig_node(*a, **k)
        for r in out:
            if cut == "drop-stock":
                r["series"].pop("Customers", None)
            else:
                r["time"] = r["time"][:-1]
                r["series"] = {c: v[:-1] for c, v in r["series"].items()}
        return out
    monkeypatch.setattr(ep.validate, "run_batch", trunc)
    monkeypatch.setattr(ep, "node_run", trunc_js)
    rep = ep.run_parity(spec, eng)
    assert rep["pass"] is False, rep["errors"]


@pytest.mark.parametrize("cut", ["empty-arrays", "pysd-short"])
def test_f5_loop_score_gate_fails_on_empty_or_short_input(bass_spec_engine, monkeypatch, cut):
    spec, _ = bass_spec_engine
    if cut == "empty-arrays":
        orig = el._node

        def fake(job):
            out = orig(job)
            for r in out:
                r["links"] = {k: (None if v is None else np.array([])) for k, v in r["links"].items()}
                r["rel"] = [np.array([]) for _ in r["rel"]]
            return out
        monkeypatch.setattr(el, "_node", fake)
    else:
        orig = el.validate.run_batch
        monkeypatch.setattr(el.validate, "run_batch", lambda *a, **k: orig(*a, **k)[:-1])
    g = el.run_ltm_gate(spec, BASS)
    assert g["pass"] is False and g["mode"] == "precomputed", g


# ---- finding 6: project checks require every case they are meant to run
def _checks_module():
    spc = importlib.util.spec_from_file_location("saas_checks", os.path.join(SAAS, "checks.py"))
    mod = importlib.util.module_from_spec(spc)
    spc.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("keep", [0, 1])
def test_f6_arr_identity_fails_without_both_cases(monkeypatch, keep):
    ck = _checks_module()
    spec = validate.load_spec(os.path.join(SAAS, "validation.toml"))
    orig = ck.validate.run_batch
    monkeypatch.setattr(ck.validate, "run_batch", lambda *a, **k: orig(*a, **k)[:keep])
    out = ck.identity(spec)
    assert out["pass"] is False, out


def test_f6_regression_fails_without_its_runs(monkeypatch):
    ck = _checks_module()
    spec = validate.load_spec(os.path.join(SAAS, "validation.toml"))
    monkeypatch.setattr(ck.validate, "run_batch", lambda *a, **k: [])
    out = ck.regression(spec)
    assert out["pass"] is False, out


# ---- audit: other gates with the same pattern
def test_audit_contrast_refuses_a_dark_theme_with_no_tokens(tmp_path):
    css = open(cc.CSS, encoding="utf-8").read()
    import re
    dark = re.search(r'^:root\[data-theme="dark"\] \{(.*?)^\}', css, re.S | re.M).group(1)
    media = re.search(r':root:where\(:not\(\[data-theme="light"\]\)\) \{(.*?)\n  \}', css, re.S).group(1)
    broken = css.replace(dark, "\n  /* emptied */\n").replace(media, "\n    /* emptied */")
    p = tmp_path / "style.css"
    p.write_text(broken, encoding="utf-8")
    with pytest.raises(ValueError, match="dark theme defines no colour tokens"):
        cc.check(str(p))


def test_audit_contrast_checks_every_declared_pair():
    rows = cc.check()
    assert len(rows) == 2 * (len(cc.TEXT) + len(cc.GRAPHIC))


def test_audit_structure_signs_need_every_run(monkeypatch):
    import explorer_structure as es
    orig = es.validate.run_batch
    monkeypatch.setattr(es.validate, "run_batch", lambda *a, **k: orig(*a, **k)[:0])
    with pytest.raises(RuntimeError, match="sign runs"):
        es.build_structure(SAAS)
