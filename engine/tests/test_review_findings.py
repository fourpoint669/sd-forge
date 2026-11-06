"""Regression tests for the read-only review of PR #3 (findings 1, 2, 3, 4 and 7; 5 is in test_explorer_intake.py and 6
in test_require_browser.py). Each test failed on b3692e5, before its fix.

1, 2, 4 (one design): a page is released only from a validated spec, current project checks and the files it embeds;
the release stamp covers every project file the build reads.
3: the parity and loop-score gates fail when the node runner returns fewer results than were asked for.
7: the pooling recomputation test fails when the page reports no flags."""
import json
import os
import shutil
import subprocess
import sys

import pytest

import build_explorer as be
import explorer_ltm as el
import explorer_parity as ep
import explorer_release as er
import export_js
import validate

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASS = os.path.join(ROOT, "projects", "bass-b2b-adoption")
SAAS = os.path.join(ROOT, "projects", "saas-churn-vs-winrate")
IMPOSSIBLE = '\n[[extreme]]\nname = "review repro: impossible"\nset = {}\nexpect = [{ var = "Customers", stat = "max", op = "<=", value = -1 }]\n'


def _copy(src, tmp_path, keep_page=True):
    d = tmp_path / os.path.basename(src)
    ignore = None if keep_page else shutil.ignore_patterns("explorer.html", "explorer_parity.json")
    shutil.copytree(src, d, ignore=ignore)
    return str(d)


def _edit_json(path, fn):
    r = json.load(open(path))
    fn(r)
    json.dump(r, open(path, "w"))


# ---- 1: results bound to the validation spec
def test_f1_build_refuses_a_spec_changed_after_validation(tmp_path):
    d = _copy(BASS, tmp_path, keep_page=False)
    open(os.path.join(d, "validation.toml"), "a").write(IMPOSSIBLE)
    with pytest.raises(be.Refused, match="validation.toml changed after validation"):
        be.build(d)


def test_f1_results_that_do_not_record_the_spec_are_refused(tmp_path):
    d = _copy(BASS, tmp_path, keep_page=False)
    _edit_json(os.path.join(d, "validation_results.json"), lambda r: r.pop("spec_files", None))
    with pytest.raises(be.Refused, match="does not record the sha256 of validation.toml"):
        be.build(d)


def test_f1_check_repo_flags_a_spec_changed_after_validation(tmp_path):
    root = tmp_path / "projects"
    shutil.copytree(BASS, root / "bass-b2b-adoption")
    open(root / "bass-b2b-adoption" / "validation.toml", "a").write(IMPOSSIBLE)
    p = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "engine", "check_repo.py"), "--projects-root", str(root)],
                       cwd=ROOT, capture_output=True, text=True)
    assert p.returncode == 1 and "validation.toml changed after validation" in p.stdout, p.stdout


# ---- 2: project checks bound to the current checks code, spec and model
def test_f2_changed_checks_code_is_refused(tmp_path):
    d = _copy(SAAS, tmp_path)
    open(os.path.join(d, "checks.py"), "a").write("\nraise RuntimeError()\n")
    with pytest.raises(er.Refused, match="checks.py changed after the project checks ran"):
        er.check_release(d)


def test_f2_checks_results_that_do_not_record_their_inputs_are_refused(tmp_path):
    d = _copy(SAAS, tmp_path)
    _edit_json(os.path.join(d, "checks_results.json"), lambda r: r.pop("inputs", None))
    with pytest.raises(er.Refused, match="checks_results.json does not record the sha256 of the files it checked"):
        er.check_release(d)


@pytest.mark.parametrize("key", ["model/saas_churn_vs_winrate.py", "model/saas_churn_vs_winrate.mdl", "validation.toml"])
def test_f2_checks_run_on_other_inputs_are_refused(tmp_path, key):
    d = _copy(SAAS, tmp_path)
    _edit_json(os.path.join(d, "checks_results.json"), lambda r: r["inputs"].__setitem__(key, "0" * 64))
    with pytest.raises(er.Refused, match=f"{key} changed after the project checks ran"):
        er.check_release(d)


def test_f2_checks_on_another_projects_files_are_bound_too(tmp_path):
    d = _copy(SAAS, tmp_path)
    ext = json.load(open(os.path.join(d, "checks_results.json")))["external_inputs"]
    assert set(ext) == {"projects/bass-b2b-adoption/validation.toml", "projects/bass-b2b-adoption/model/bass_b2b_adoption.mdl",
                        "projects/bass-b2b-adoption/model/bass_b2b_adoption.py"}
    _edit_json(os.path.join(d, "checks_results.json"),
               lambda r: r["external_inputs"].__setitem__("projects/bass-b2b-adoption/validation.toml", "0" * 64))
    with pytest.raises(er.Refused, match="projects/bass-b2b-adoption/validation.toml changed after the project checks ran"):
        er.check_release(d)


# ---- 3: gates fail on incomplete runner output
@pytest.fixture(scope="module")
def bass_spec_engine():
    spec = validate.load_spec(os.path.join(BASS, "validation.toml"))
    return spec, export_js.emit_js(export_js.load_ir(spec["model"]["py_path"]))


def test_f3_parity_fails_when_the_runner_returns_fewer_runs(bass_spec_engine, monkeypatch):
    spec, eng = bass_spec_engine
    orig = ep.node_run
    monkeypatch.setattr(ep, "node_run", lambda *a, **k: orig(*a, **k)[:1])
    rep = ep.run_parity(spec, eng)
    assert rep["pass"] is False
    assert any("runner returned 1 results for 35 settings" in e["error"] for e in rep["errors"]), rep["errors"]


def test_f3_parity_still_passes_with_complete_output(bass_spec_engine):
    spec, eng = bass_spec_engine
    rep = ep.run_parity(spec, eng)
    assert rep["pass"] is True and rep["n_runs"] == len(ep.lever_settings(spec, ep.N_RANDOM, ep.SEED))


@pytest.mark.parametrize("cut", ["empty", "one", "no-links"])
def test_f3_loop_score_gate_fails_on_incomplete_output(bass_spec_engine, monkeypatch, cut):
    spec, _ = bass_spec_engine
    orig = el._node

    def fake(job):
        out = orig(job)
        if cut == "empty":
            return []
        if cut == "one":
            return out[:1]
        for r in out:
            r["links"] = {}
        return out
    monkeypatch.setattr(el, "_node", fake)
    g = el.run_ltm_gate(spec, BASS)
    assert g["pass"] is False and g["mode"] == "precomputed", g


# ---- 4: the stamp covers everything the page rests on
@pytest.mark.parametrize("rel", ["mc_bands.csv", "loop_dominance.json", "summary.md", "assumptions_register.md",
                                 "delay_audit.json", "explorer_glossary.toml", "explorer.toml", "explorer_intake.toml"])
def test_f4_changing_an_embedded_file_after_the_build_is_flagged(tmp_path, rel):
    d = _copy(BASS, tmp_path)
    assert er.shipped_errors(d) == []
    open(os.path.join(d, rel), "a").write("\n")
    assert any(f"{rel} changed since the page was built" in e for e in er.shipped_errors(d))


def test_f4_stamp_covers_every_project_file_the_build_reads(tmp_path):
    """Trace every file the build opens (audit hook) and require each project file it read to be stamped."""
    d = _copy(SAAS, tmp_path, keep_page=False)
    real = os.path.realpath(d)
    seen = set()

    def hook(event, args):
        if event == "open" and isinstance(args[0], str) and (len(args) < 2 or not args[1] or "r" in str(args[1])):
            p = os.path.realpath(args[0])
            if p.startswith(real + os.sep):
                seen.add(os.path.relpath(p, real).replace(os.sep, "/"))
    sys.addaudithook(hook)
    try:
        be.build(d)
    finally:
        real = "/nonexistent-after-build"          # audit hooks cannot be removed; this one goes quiet
    stamped = set(json.load(open(os.path.join(d, "explorer_parity.json")))["release"]["files"])
    read = seen - {"explorer.html", "explorer_parity.json"}
    assert read and read <= stamped, sorted(read - stamped)


# ---- 7: the pooling recomputation test cannot pass on missing flags
def test_f7_pooling_test_fails_when_the_page_reports_no_flags():
    import test_explorer_dynamic as td
    import explorer_structure
    spec = validate.load_spec(os.path.join(SAAS, "validation.toml"))
    sets = [s for s in ep.lever_settings(spec, n_random=5, seed=ep.SEED) if s[0] == "base" or s[0].startswith("random")]
    structure = explorer_structure.build_structure(SAAS)
    assert structure["pooling"]["capped"]
    dyn = {"_data": {"structure": structure}, "_spec": spec, "pooling_defaults": {"bind": 1, "build": 0.05, "window": 6},
           "_sets": sets, "ripple_baseline": validate.base_params(spec), "pooling": [{"flags": []} for _ in sets]}
    with pytest.raises(AssertionError):
        td.test_pooling_flags_equal_a_pysd_recomputation(dyn)
