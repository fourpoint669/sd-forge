"""engine/build_explorer.py: refusal gates, single self-contained HTML, shipped engine == parity-tested engine."""
import json
import os
import re
import shutil
import subprocess

import pytest

import build_explorer as be
import explorer_meta as em
import explorer_parity as ep
import export_js
import validate

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASS = os.path.join(ROOT, "projects", "bass-b2b-adoption")
SAAS = os.path.join(ROOT, "projects", "saas-churn-vs-winrate")
EXTERNAL = re.compile(r"""(?:\b(?:src|href|action|poster|data)\s*=\s*["']?\s*(?:https?:)?//)|@import|url\(\s*["']?(?:https?:)?//""",
                      re.I)


def copy_project(src, tmp_path):
    dst = tmp_path / os.path.basename(src)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("explorer.html", "explorer_parity.json"))
    return str(dst)


@pytest.fixture(scope="module")
def bass_build(tmp_path_factory):
    d = copy_project(BASS, tmp_path_factory.mktemp("bass"))
    rep = be.build(d)
    return d, rep, open(os.path.join(d, "explorer.html"), encoding="utf-8").read()


BASELINES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "baselines")


# the approved change to engine/loop_detector.py: analyze() also reports how many of the run's time steps carry any
# non-zero loop score, so validate.py T8 can refuse a model whose loop-strength view would be empty. Records only: no
# link score, loop score, polarity or dominance rule changes. Approved 2026-11-02 (user), same report as above.
APPROVED_LOOP_DETECTOR_DIFF = {
    "-": [],
    "+": ['    # Steps where at least one loop has a non-zero score. Where tot is 0 every relative score is NaN, so there is', '    # no dominant loop and nothing for a loop-strength chart to draw at that step; 0 of n means the whole view is', '    # empty. Reported so a caller can refuse to ship that silently (validate.py T8).', '            "scored_steps": int(np.count_nonzero(tot > 0)) if len(loops) else 0, "n_steps": int(t.size),'],
}


def test_protected_engine_files_differ_only_by_the_approved_change():
    """engine/loop_detector.py equals its baseline snapshot (taken from the commit before the explorer work began; the
    snapshot is kept in engine/tests/baselines/ so this does not depend on the git history) apart from one approved
    change, enumerated above. Any other edit fails here."""
    res = subprocess.run(["git", "diff", "--no-index", "-U0", os.path.join(BASELINES, "loop_detector_baseline.py"),
                          os.path.join(ROOT, "engine", "loop_detector.py")], capture_output=True, text=True)
    assert res.returncode in (0, 1) and res.stderr == ""           # 1 = they differ, which is expected
    got = {"-": [], "+": []}
    for line in res.stdout.splitlines():
        if line[:1] in "+-" and not line.startswith(("+++", "---")):
            got[line[0]].append(line[1:])
    assert got == APPROVED_LOOP_DETECTOR_DIFF


# the approved changes to engine/validate.py: record the sha256 of the model files and spec it validated and of the
# result files it wrote (record-only), fail-closed count and completeness checks (run_batch, T3, Monte Carlo, the
# results-file write). No tolerance or threshold
# changes. Any other edit fails here.
# Approved 2026-11-02 (user, after an empty loop-strength view was reported in use on projects/car-dealership-profit):
# T8 also refuses a base run in which no loop carries a score at any time step, because the loop-strength view of
# every page built from such a model is empty; dominance_empty_at_base declares the reason when that is deliberate,
# and a declaration that is not needed fails too. No existing tolerance or threshold is changed.
# Approved 2026-11-03 (user, by merging pull request #1, whose description flagged change 3 below for a read first):
# three changes from a security and defect review of the whole repository.
#   1. parse_units' take() raises UnitError at the end of the token list, so a truncated unit ("Widgets*") is one T1
#      problem instead of an IndexError that escapes check_units and aborts the whole run with an empty test table;
#   2. load_spec refuses a model.mdl / model.py that lands outside the project folder (absolute path, "..", or a
#      symlink out), because the .py it names is imported - executed - by every run;
#   3. run_all returns before any model runs when T0_translation failed: the committed .py is not what PySD writes
#      from the .mdl, so it is never executed. The ast-only tests above it (T1, T1b, T1c) still report their problems.
#      This CHANGES WHAT VALIDATION DOES - a project whose .py has drifted now gets a fatal with no T3-T8 numbers
#      instead of a full report with T0 marked FAIL. That was the judgement call the approval above covers.
# No tolerance or threshold is changed. The diff below was regenerated from the real file; the only lines it gained
# over the previously approved list are those three changes (verified line by line, nothing approved was removed).
APPROVED_VALIDATE_DIFF = {
    "-": [
        '  validation_results.json   every test, its numbers and pass/fail (always written)',
        "                   override must lie in that parameter's [low, high]; dominance is still from the true base run",
        '        for start, dfs, err in ex.map(go, chunks):',
        '            out[start:start + len(dfs)] = dfs',
        '    spec["model"]["mdl_path"] = os.path.join(base, spec["model"]["mdl"])',
        '    spec["model"]["py_path"] = os.path.join(base, spec["model"]["py"])',
        '    R = {"model": m["name"], "tests": {}}',
        '        part = [d if d is not None and np.all(np.isfinite(d.to_numpy(float))) else None for d in part]',
        '    json.dump(R, open(os.path.join(d, "validation_results.json"), "w"), indent=1, default=str)',
        '    write_outputs(spec, R, results)',
    ],
    "+": [
        '  validation_results.json   every test, its numbers and pass/fail, the sha256 of the model .mdl and .py it',
        '                            validated and of the validation spec, and the sha256 of each result file below as',
        '                            written by this run (always written, after the result files)',
        "                   override must lie in that parameter's [low, high]; dominance is still from the true base run.",
        '                   A base run in which no loop carries a score at any time step makes the loop-strength view of',
        '                   every page built from the model empty; that fails unless dominance_empty_at_base gives the',
        '                   reason, and a declaration that is not needed fails too',
        'import hashlib',
        'CONTROL_COLUMNS = ("FINAL TIME", "INITIAL TIME", "SAVEPER", "TIME STEP")',
        '',
        '',
        'def model_controls(py):',
        '    """initial_time, final_time, time_step, saveper as written in the PySD model file (_control_vars)."""',
        '    tree = ast.parse(open(py, encoding="utf-8").read())',
        '    exprs = {}',
        '    for node in tree.body:',
        '        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_control_vars" for t in node.targets):',
        '            exprs = {k.value: v.body for k, v in zip(node.value.keys, node.value.values) if isinstance(v, ast.Lambda)}',
        '    out = {}',
        '',
        '    def value(k, seen=()):',
        '        e = exprs[k]',
        '        if k in seen:',
        '            raise ValueError(f"_control_vars: {k} refers to itself")',
        '        if isinstance(e, ast.Call) and isinstance(e.func, ast.Name) and not e.args and e.func.id in exprs:',
        '            return value(e.func.id, seen + (k,))       # e.g. "saveper": lambda: time_step()',
        '        return float(ast.literal_eval(e))',
        '    for k in ("initial_time", "final_time", "time_step", "saveper"):',
        '        out[k] = value(k)',
        '    return out',
        '',
        '',
        'def model_columns(py):',
        '    """The columns a full PySD run returns: every model component except the time controls."""',
        '    return sorted(c.name for c in ld.parse_model(py).comps.values() if c.name not in CONTROL_COLUMNS + ("Time",))',
        '',
        '',
        'def expected_times(initial, final, saveper, time_step=None):',
        '    """The saved time grid of a run: initial, initial + saveper, ..., final (PySD saves the final step too)."""',
        '    n = int(round((final - initial) / saveper))',
        '    return initial + saveper * np.arange(n + 1)',
        '',
        '',
        'def frame_problem(df, times, columns):',
        '    """None when a result frame has exactly the expected time grid and every expected column; else the reason.',
        '    The expectation comes from the model and the spec (expected_times, model_columns or the requested columns),',
        '    never from the frame. An empty or missing frame is a problem."""',
        '    if df is None:',
        '        return "no result"',
        '    idx = np.asarray(df.index, dtype=float)',
        '    if len(idx) != len(times):',
        '        return f"{len(idx)} time points, expected {len(times)}"',
        '    if not np.allclose(idx, times, rtol=0.0, atol=1e-9 * max(1.0, float(np.max(np.abs(times))))):',
        '        return "time grid differs from the expected one"',
        '    missing = sorted(set(columns) - set(df.columns))',
        '    if missing:',
        '        return f"missing columns {missing[:5]}" + (" ..." if len(missing) > 5 else "")',
        '    return None',
        '',
        '',
        'def _place_chunk(out, start, expected, dfs, errors):',
        '    """Put one chunk\'s frames into `out` without ever changing its length: a chunk that came back with a different',
        '    number of frames than runs counts as failed (None for each of its runs)."""',
        '    if len(dfs) != expected:',
        '        errors.append(f"worker returned {len(dfs)} frames for {expected} runs (runs {start}-{start + expected - 1} counted as failed)")',
        '        dfs = [None] * expected',
        '    out[start:start + expected] = dfs',
        '',
        '',
        '        for (start, rs), (_, dfs, err) in zip(chunks, ex.map(go, chunks)):',
        '            _place_chunk(out, start, len(rs), dfs, errors)',
        "        if pos >= len(toks):                           # a truncated unit ('Widgets*', '1/', 'Month^', '(Firm')",
        '            raise UnitError(f"cannot parse units \'{s}\'")',
        '    real_base = os.path.realpath(base)',
        '    for k in ("mdl", "py"):',
        "        # the .py named here is imported (executed) by every run: an absolute path, a '..' or a symlink out of the",
        '        # project would run a file the project does not contain. Keep the joined path as written, check where it lands.',
        '        joined = os.path.join(base, spec["model"][k])',
        '        landing = os.path.realpath(joined)',
        '        if landing != real_base and os.path.commonpath([landing, real_base]) != real_base:',
        '            raise ValueError(f"model.{k} must be inside the project folder, not {spec[\'model\'][k]!r}")',
        '        spec["model"][k + "_path"] = joined',
        'def model_hashes(spec):',
        '    """sha256 of the model files a run validates (the .mdl and its PySD .py), keyed by path relative to the spec, so',
        '    later tools can tell whether the model changed after validation. Records only; checks nothing."""',
        '    m = spec["model"]',
        '    return {os.path.relpath(p, spec["_dir"]).replace(os.sep, "/"): hashlib.sha256(open(p, "rb").read()).hexdigest()',
        '            for p in (m["mdl_path"], m["py_path"])}',
        '',
        '',
        '    R = {"model": m["name"], "model_files": model_hashes(spec),',
        '         "spec_files": {os.path.basename(spec_path): hashlib.sha256(open(spec_path, "rb").read()).hexdigest()}, "tests": {}}',
        '    if not T["T0_translation"]["pass"]:',
        '        # Every run below imports the committed .py (pysd.load executes it). T0 having failed means that file is not',
        '        # what PySD writes from the .mdl, so it is not run at all: reporting a mismatch after executing it is too late.',
        '        # The tests above read it with ast only, so their problems are still reported.',
        '        R["fatal"] = ("the committed model .py is not a fresh PySD translation of the .mdl "',
        '                      "(see T0_translation); no model runs performed")',
        '        R["all_pass"] = False',
        '        return spec, R, None',
        '    if len(E) != len(ext_cases):   # every extreme case must come back; zip() below would skip the missing ones',
        '        fails.append(f"T3: {len(E)} results for {len(ext_cases)} extreme cases")',
        '    ctl = model_controls(py)',
        '    grid, all_cols = expected_times(ctl["initial_time"], m["final_time"], save, m["time_step"]), model_columns(py)',
        '        prob = frame_problem(df, grid, all_cols)     # every case must hold the whole grid and every column',
        '        if prob:',
        '            fails.append(f"{label}: incomplete run ({prob})")',
        '            continue',
        '        # A loop-strength view with nothing in it. Where no loop has a non-zero score at a step, every relative score',
        "        # there is NaN: no dominant loop, and nothing for the explorer's loop-strength chart to draw. 0 of n steps",
        '        # means the whole view is empty on every page built from this model. That can be a deliberate base case (every',
        '        # optional feedback switched off), so it is allowed - but only when the reason is declared, never silently.',
        '        empty = spec.get("dominance_empty_at_base")',
        '        declared = isinstance(empty, str) and empty.strip() != ""',
        '        if empty is not None and not declared:',
        '            probs.append("dominance_empty_at_base must be a non-empty string giving the reason")',
        '        if la["n_steps"] and not la["scored_steps"] and not declared:',
        '            probs.append(f"no loop has a non-zero score at any of the {la[\'n_steps\']} time steps of the base run, so "',
        '                         "the loop-strength view of every page built from this model is empty. Change the base case, "',
        '                         "or state why in dominance_empty_at_base.")',
        '        if declared and la["scored_steps"]:',
        '            probs.append(f"dominance_empty_at_base is declared but {la[\'scored_steps\']} of {la[\'n_steps\']} base-run "',
        '                         "time steps do carry a loop score: remove the declaration.")',
        '                         "scored_steps": la["scored_steps"], "n_steps": la["n_steps"],',
        '                         "dominance_empty_at_base": empty if declared else None,',
        '    ctl = model_controls(py)',
        '    grid = expected_times(ctl["initial_time"], time_kw["final_time"], time_kw["saveper"], time_kw["time_step"])',
        '        part = [d if d is not None and frame_problem(d, grid, cols) is None and np.all(np.isfinite(d.to_numpy(float)))',
        '                else None for d in part]          # an incomplete run (wrong grid, missing columns, empty) is a failed run',
        '        R["output_files"] = {}',
        '        json.dump(R, open(os.path.join(d, "validation_results.json"), "w"), indent=1, default=str)',
        '    # record-only: the sha256 of each result file as this run wrote it, so later tools can tell if one was edited',
        '    R["output_files"] = {f: hashlib.sha256(open(os.path.join(d, f), "rb").read()).hexdigest() for f in sorted(produced)}',
        '    json.dump(R, open(os.path.join(d, "validation_results.json"), "w"), indent=1, default=str)',
        '    try:',
        '        write_outputs(spec, R, results)',
        "    except Exception as e:  # noqa: BLE001 - never leave an earlier run's results file behind: record a failure, re-raise",
        '        R = {k: v for k, v in R.items() if k != "_loop_analysis"}',
        '        R.update(all_pass=False, output_files={}, fatal=f"write_outputs failed: {type(e).__name__}: {e}"[:500])',
        '        json.dump(R, open(os.path.join(spec["_dir"], "validation_results.json"), "w"), indent=1, default=str)',
        '        raise',
    ],
}


APPROVED_GOAL_SEEKING = {
    "-": ['ANALYTIC = {"bass": bass_cumulative}'],
    "+": ['def goal_seeking(t, G, y0, tau):',
          '    """Closed form of a first-order approach to a goal: y\' = (G - y)/tau, y(0) = y0."""',
          '    return G + (y0 - G) * np.exp(-np.asarray(t, float) / tau)', '', '',
          'ANALYTIC = {"bass": bass_cumulative, "goal_seeking": goal_seeking}'],
}


# Approved 2026-11-03 (user instruction "fix all the errors", which covered the security review's finding that an
# untrusted .mdl runs code): translate() refuses a generated model file that is not plain PySD output. The screen itself
# lives in engine/generated_code_check.py; validate.py only imports it and calls it on each fresh translation.
APPROVED_GENERATED_CODE_SCREEN = {
    "-": ['    return os.path.splitext(dst)[0] + ".py"'],
    "+": ['import generated_code_check  # noqa: E402',
          '    py = os.path.splitext(dst)[0] + ".py"',
          '    problems = generated_code_check.problems(py)',
          '    if problems:',
          '        raise RuntimeError("translation refused: the generated model file contains code that a PySD translation does "',
          '                           "not produce (a model comment or name may be breaking out of its string): "',
          '                           + "; ".join(problems[:3]))',
          '    return py'],
}


# Approved 2026-11-06 (user, answering "Approve the edit" when the Windows CI run showed that a timed-out worker's child
# process survives: the venv python.exe starts the real interpreter as a child, so Popen.kill() alone ends only the
# launcher). _kill_tree ends the whole tree with taskkill /T on Windows. POSIX behaviour is unchanged.
APPROVED_WINDOWS_TREE_KILL = {
    "+": ["        # Windows: the venv's python.exe starts the real interpreter as a child, so p.kill() alone leaves it running.",
          "        # taskkill /T ends the worker and every process it started.",
          "        try:",
          '            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True, timeout=KILL_GRACE_S)',
          "        except (OSError, subprocess.SubprocessError):",
          "            pass"],
}


def test_validate_py_differs_only_by_the_approved_hash_recording():
    res = subprocess.run(["git", "diff", "--no-index", "-U0", os.path.join(BASELINES, "validate_baseline.py"),
                          os.path.join(ROOT, "engine", "validate.py")], capture_output=True, text=True)
    assert res.returncode in (0, 1) and res.stderr == ""            # 1 = they differ, which is expected
    out = res.stdout.splitlines()
    got = {"-": [], "+": []}
    for line in out:
        if line[:1] in "+-" and not line.startswith(("+++", "---")):
            got[line[0]].append(line[1:])
    # approved 2026-10-30 (user, gate 5 of projects/car-dealership-profit): the `goal_seeking` analytic reference for T5.
    # Removed as one contiguous block, so any other edit, or a changed goal_seeking, still fails.
    # the Windows block sits between the two lines of the generated-code screen's imports, so it is removed first
    for name, approved in (("goal_seeking", APPROVED_GOAL_SEEKING), ("Windows process-tree kill", APPROVED_WINDOWS_TREE_KILL),
                           ("generated-code screen", APPROVED_GENERATED_CODE_SCREEN)):
        for sign, block in approved.items():
            n = len(block)
            hits = [i for i in range(len(got[sign]) - n + 1) if got[sign][i:i + n] == block]
            assert len(hits) == 1, f"the approved {name} diff is missing or changed ({sign})"
            del got[sign][hits[0]:hits[0] + n]
    # blank lines are ignored: git pairs them differently when a block is inserted next to them
    assert {k: [x for x in v if x.strip()] for k, v in got.items()} == \
        {k: [x for x in v if x.strip()] for k, v in APPROVED_VALIDATE_DIFF.items()}


def test_refuses_when_the_model_changed_after_validation(tmp_path):
    d = copy_project(BASS, tmp_path)
    py = os.path.join(d, "model", "bass_b2b_adoption.py")
    open(py, "a").write("\n")
    with pytest.raises(be.Refused, match="bass_b2b_adoption.py changed after validation"):
        be.build(d)


def test_refuses_when_validation_results_do_not_record_model_hashes(tmp_path):
    d = copy_project(BASS, tmp_path)
    p = os.path.join(d, "validation_results.json")
    r = json.load(open(p))
    r.pop("model_files", None)
    json.dump(r, open(p, "w"))
    with pytest.raises(be.Refused, match="does not record the sha256"):
        be.build(d)


@pytest.mark.parametrize("edit", [False, True], ids=["unedited-passes", "edited-model-fails"])
def test_check_repo_compares_model_hashes(tmp_path, edit):
    import sys
    root = tmp_path / "projects"
    shutil.copytree(BASS, root / "bass-b2b-adoption")
    if edit:
        mdl = root / "bass-b2b-adoption" / "model" / "bass_b2b_adoption.mdl"
        mdl.write_text(mdl.read_text() + "\n")
    p = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "engine", "check_repo.py"), "--projects-root", str(root)],
                       cwd=ROOT, capture_output=True, text=True)
    if edit:
        assert p.returncode == 1 and "bass_b2b_adoption.mdl changed after validation" in p.stdout, p.stdout
    else:
        assert p.returncode == 0, p.stdout


def test_refuses_when_validation_report_is_not_pass(tmp_path):
    d = copy_project(BASS, tmp_path)
    p = os.path.join(d, "validation_report.md")
    txt = open(p).read()     # read before opening for write (which truncates)
    assert "Overall: **PASS**" in txt
    open(p, "w").write(txt.replace("Overall: **PASS**", "Overall: **FAIL**"))
    with pytest.raises(be.Refused, match="validation_report.md"):
        be.build(d)


def test_refuses_when_validation_results_not_all_pass(tmp_path):
    d = copy_project(BASS, tmp_path)
    p = os.path.join(d, "validation_results.json")
    r = json.load(open(p))
    r["all_pass"] = False
    json.dump(r, open(p, "w"))
    with pytest.raises(be.Refused, match="all_pass"):
        be.build(d)


def test_refuses_when_checks_results_missing(tmp_path):
    d = copy_project(SAAS, tmp_path)
    os.remove(os.path.join(d, "checks_results.json"))
    with pytest.raises(be.Refused, match="checks_results.json"):
        be.build(d)


def test_refuses_when_checks_results_fail(tmp_path):
    d = copy_project(SAAS, tmp_path)
    p = os.path.join(d, "checks_results.json")
    r = json.load(open(p))
    r["all_pass"] = False
    json.dump(r, open(p, "w"))
    with pytest.raises(be.Refused, match="checks_results.json"):
        be.build(d)


def test_refuses_on_missing_metadata(tmp_path):
    d = copy_project(BASS, tmp_path)
    reg = os.path.join(d, "assumptions_register.md")
    txt = open(reg).read()   # read before opening for write (which truncates)
    open(reg, "w").write("\n".join(l for l in txt.splitlines() if not l.startswith("| win rate")) + "\n")
    with pytest.raises(em.MissingMetadata, match=r"^parameter 'win rate' has no row in assumptions_register.md$"):
        be.build(d)


def test_html_has_no_external_references(bass_build):
    _, rep, html = bass_build
    assert not EXTERNAL.search(html)
    assert "<link" not in html.lower()
    assert not re.search(r"<script[^>]+src=", html, re.I)
    assert rep["external_refs"] == []


def test_html_size_reported_and_under_target(bass_build):
    _, rep, html = bass_build
    print(f"\nexplorer.html size: {rep['size_bytes']} bytes")
    assert rep["size_bytes"] == len(html.encode("utf-8"))
    assert rep["size_bytes"] < 3 * 1024 * 1024


def test_shipped_engine_is_the_parity_tested_engine(bass_build):
    d, rep, html = bass_build
    shipped = be.extract_script(html, "sd-engine")
    spec = validate.load_spec(os.path.join(d, "validation.toml"))
    assert shipped == export_js.emit_js(export_js.load_ir(spec["model"]["py_path"]))
    again = ep.run_parity(spec, shipped)
    assert again["pass"] and rep["parity"]["pass"]
    assert rep["parity"]["max_scale_rel"] <= ep.TOL and rep["parity"]["max_pointwise_rel"] <= ep.TOL


def test_headline_metrics_match_validate_stat(bass_build):
    _, rep, _ = bass_build
    h = rep["parity"]["headline"]
    assert h["n_values"] >= 10
    assert h["max_rel"] <= ep.TOL


def test_parity_report_written(bass_build):
    d, rep, _ = bass_build
    saved = json.load(open(os.path.join(d, "explorer_parity.json")))
    assert saved["pass"] is True
    assert saved["engine_sha256"] == rep["engine_sha256"]


def test_page_data_levers_and_limits(bass_build):
    d, _, html = bass_build
    data = json.loads(be.extract_script(html, "sd-data"))
    spec = validate.load_spec(os.path.join(d, "validation.toml"))
    assert [l["name"] for l in data["levers"]] and {l["name"] for l in data["levers"]} == set(spec["parameters"])
    for l in data["levers"]:
        v = spec["parameters"][l["name"]]
        assert (l["low"], l["high"], l["base"]) == (v["low"], v["high"], v["base"])
        m = data["variables"][l["name"]]
        assert m["source"] and m["confidence"] and m["unit"] and m["definition"]
    assert data["model_limits"] == em.model_limits(open(os.path.join(d, "summary.md")).read())


def test_bands_attach_to_first_policy_only(bass_build):
    _, _, html = bass_build
    data = json.loads(be.extract_script(html, "sd-data"))
    sets = data["bands"]
    assert [b["preset"] for b in sets] == [data["presets"][0]["name"]]
    assert "Customers" in sets[0]["series"]
    assert sets[0]["label"].startswith("Monte Carlo")


def test_build_is_deterministic(bass_build, tmp_path):
    d, _, html = bass_build
    d2 = copy_project(BASS, tmp_path)
    be.build(d2)
    assert open(os.path.join(d2, "explorer.html"), encoding="utf-8").read() == html


@pytest.fixture(scope="module")
def saas_build(tmp_path_factory):
    d = copy_project(SAAS, tmp_path_factory.mktemp("saas"))
    rep = be.build(d)
    return d, rep, open(os.path.join(d, "explorer.html"), encoding="utf-8").read()


def test_saas_parity_including_headline_metrics(saas_build):
    _, rep, html = saas_build
    p = rep["parity"]
    print(f"\nsaas parity: {p['n_runs']} runs, A = {p['max_scale_rel']:.3e}, B = {p['max_pointwise_rel']:.3e}, "
          f"headline {p['headline']['n_values']} values max {p['headline']['max_rel']:.3e}; size {rep['size_bytes']} bytes")
    assert p["pass"] and p["max_scale_rel"] <= ep.TOL and p["max_pointwise_rel"] <= ep.TOL
    assert p["headline"]["n_values"] == p["n_runs"] * 8 and p["headline"]["max_rel"] <= ep.TOL
    assert rep["size_bytes"] < 3 * 1024 * 1024 and not EXTERNAL.search(html)


def test_saas_bands_attach_to_named_presets(saas_build):
    _, _, html = saas_build
    data = json.loads(be.extract_script(html, "sd-data"))
    by = {b["preset"]: b for b in data["bands"]}
    assert by["no programme"]["source"] == "mc_bands.csv"
    assert {"50/50 split", "churn only", "win rate only"} <= set(by)
    assert all(by[p]["source"] == "scenario_bands.csv" for p in by if p != "no programme")
    assert set(by["50/50 split"]["series"]) == {"ARR", "Customers"}


def test_saas_fixed_levers_and_illustrative_flags(saas_build):
    _, _, html = saas_build
    data = json.loads(be.extract_script(html, "sd-data"))
    fixed = sorted(l["name"] for l in data["levers"] if l["fixed"])
    assert fixed == ["churn share phase 1", "churn share phase 2", "phase switch month"]
    ill = sorted(k for k, v in data["variables"].items() if v["illustrative"])
    assert ill == ["initial sales capacity", "initial total market", "total programme budget"]


# ---- the inlined data island ------------------------------------------------------------------------------------------

def _blob(html):
    return re.search(r'<script id="sd-data" type="application/json">(.*?)</script>', html, re.S).group(1)


@pytest.mark.parametrize("text", [
    "x <= 3",                                  # an ordinary comparison, in the shipped projects today
    "<!--<script>",                            # opens script-data-double-escaped: </script> then stops closing the element
    "</script><img src=x onerror=alert(1)>",
    "<!-- <script> -->",
])
def test_the_data_island_survives_markup_in_model_text(text):
    """A '<' in a variable's comment or equation must not be able to end the element early: the page would render as a
    bare shell, with the engine swallowed as JSON text, and the build would still report success."""
    html = be.assemble("t", {"definition": text}, "var a=1;", "var b=2;", "var c=3;")
    blob = _blob(html)
    assert "<" not in blob
    assert json.loads(blob) == {"definition": text}
    assert be.extract_script(html, "sd-engine") == "var a=1;"          # the engine is still its own element


def test_no_shipped_page_has_a_raw_angle_bracket_in_its_data_island():
    for name in ("bass-b2b-adoption", "saas-churn-vs-winrate", "car-dealership-profit"):
        page = os.path.join(ROOT, "projects", name, "explorer.html")
        if os.path.exists(page):
            assert "<" not in _blob(open(page, encoding="utf-8").read()), name


def test_a_script_that_could_close_its_own_element_is_refused_not_a_traceback():
    """export_js escapes '<' in everything model-derived, so this is the backstop; it refuses like every other gate."""
    with pytest.raises(be.Refused, match="</script"):
        be.assemble("t", {}, "var a=1;</script><img src=x onerror=alert(1)>", "var b=2;", "var c=3;")


def test_a_template_marker_appearing_twice_is_refused_not_a_traceback():
    with pytest.raises(be.Refused, match="exactly once"):
        be.assemble("t", {}, "var a=1;/*@APP@*/", "var b=2;", "var c=3;")


def test_an_over_size_page_is_refused_before_anything_is_written(tmp_path, monkeypatch):
    """The module docstring promises nothing is written on refusal; the size limit used to be checked only by main(),
    after build() had already written the page and a parity record saying it passed."""
    d = copy_project(BASS, tmp_path)
    monkeypatch.setattr(be, "SIZE_TARGET", 1024)
    with pytest.raises(be.Refused, match="nothing written"):
        be.build(d)
    assert not os.path.exists(os.path.join(d, "explorer.html"))
    assert not os.path.exists(os.path.join(d, "explorer_parity.json"))
