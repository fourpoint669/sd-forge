"""Gate for live link and loop strength on the explorer page (M3c).

Usage:  python -I engine/explorer_ltm.py projects/<model>

The page computes loops-that-matter link scores and relative loop scores for its own run in JavaScript
(explorer_template/ltm.js on the equations from export_js.emit_eqs). The gate compares them with
engine/loop_detector.py (link_scores, analyze) on PySD runs saved every dt, for the base case and 5 seeded random lever
settings inside the validated ranges, with the fixed metric: per series S = max_t |py|, max_t |js - py| / S <= 1e-9
(all-zero series exact; non-finite values must match in place).
  end to end      JS engine run -> JS scores   vs   PySD run -> loop_detector        (decides live vs precomputed)
  implementation  PySD run -> JS scores        vs   PySD run -> loop_detector        (checks the port by itself)
Pass -> the page computes link and loop strength live. Fail -> the page shows precomputed base-case values from
loop_detector, labelled as such, and the report says why.
"""
import json
import math
import os
import shutil
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import explorer_parity as ep  # noqa: E402
import export_js  # noqa: E402
import loop_detector as ld  # noqa: E402  (read-only dependency)
import validate  # noqa: E402  (read-only dependency)

TOL = 1e-9
RUNNER = os.path.join(HERE, "explorer_ltm_runner.js")
LTM_JS = os.path.join(HERE, "explorer_template", "ltm.js")


def settings(spec):
    return [s for s in ep.lever_settings(spec, n_random=5, seed=ep.SEED) if s[0] == "base" or s[0].startswith("random")]


def loops_of(project_dir):
    return [lp["py"] for lp in json.load(open(os.path.join(project_dir, "loop_dominance.json")))["loops"]]


def _node(job):
    node = shutil.which("node")
    if not node:
        raise RuntimeError("node not found: the LTM gate cannot run")
    p = subprocess.run([node, RUNNER], input=json.dumps(job), capture_output=True, text=True, timeout=900)
    if p.returncode != 0:
        raise RuntimeError("LTM runner failed: " + p.stderr[-800:])
    out = json.loads(p.stdout)
    dec = lambda a: np.array([float(x) if isinstance(x, str) else x for x in a], dtype=float)  # noqa: E731
    for r in out:
        r["time"] = dec(r["time"])
        r["links"] = {k: (None if v is None else dec(v)) for k, v in r["links"].items()}
        r["rel"] = [dec(a) for a in r["rel"]]
    return out


def _metric(py, js):
    if py is None or js is None:
        return 0.0 if (py is None and js is None) else math.inf
    return ep.parity_metrics(py, js)["scale"]


def _compare(pys, jss, loop_ids):
    """Every link and loop series of every run must be compared: a run, link or loop missing from the JS side counts
    as an infinite difference, so incomplete runner output can never pass."""
    link_max, loop_max, n_link, n_loop, worst = 0.0, 0.0, 0, 0, {}
    want_link = sum(len(py["links"]) for _, py in pys)
    want_loop = len(pys) * len(loop_ids)
    complete = len(jss) == len(pys)
    for (lab, py), js in zip(pys, jss):
        for e, arr in py["links"].items():
            m = _metric(arr, js["links"][e]) if e in js["links"] else math.inf
            m = math.inf if m != m else m
            n_link += 1
            if m >= link_max:
                link_max, worst["link"] = m, (lab, e)
        for i, lid in enumerate(loop_ids):
            m = _metric(np.asarray(py["rel"][lid], float), js["rel"][i]) if i < len(js["rel"]) else math.inf
            m = math.inf if m != m else m
            n_loop += 1
            if m >= loop_max:
                loop_max, worst["loop"] = m, (lab, lid)
    complete = complete and n_link == want_link > 0 and n_loop == want_loop > 0
    if not complete:
        link_max = loop_max = math.inf
    return {"max_link": link_max, "max_loop": loop_max, "n_link": n_link, "n_loop": n_loop, "worst": worst,
            "expected_link": want_link, "expected_loop": want_loop, "complete": complete}


def run_ltm_gate(spec, project_dir, ltm_text=None):
    py_path = spec["model"]["py_path"]
    ir = export_js.load_ir(py_path)
    engine, eqs = export_js.emit_js(ir), export_js.emit_eqs(py_path)
    ltm = ltm_text if ltm_text is not None else open(LTM_JS, encoding="utf-8").read()
    model = ld.parse_model(py_path)
    sets = settings(spec)
    dfs = validate.run_batch(py_path, [{"params": p, "saveper_dt": True} for _, p in sets])
    loops = loops_of(project_dir)
    ctl = validate.model_controls(py_path)
    grid = validate.expected_times(ctl["initial_time"], ctl["final_time"], ctl["time_step"], ctl["time_step"])
    cols = validate.model_columns(py_path)
    bad = [lab for (lab, _), df in zip(sets, dfs) if validate.frame_problem(df, grid, cols)]   # every dt, every column
    if len(dfs) != len(sets) or bad:
        raise_or = bad
        return {"labels": [lab for lab, _ in sets], "n_runs": len(sets), "n_link_series": 0, "n_loop_series": 0,
                "end_to_end": {"max_link": math.inf, "max_loop": math.inf, "n_link": 0, "n_loop": 0, "complete": False,
                               "error": f"PySD returned {len(dfs)} results for {len(sets)} settings; incomplete: {raise_or}"},
                "implementation": {"max_link": math.inf, "max_loop": math.inf, "n_link": 0, "n_loop": 0, "complete": False},
                "tolerance": TOL, "pass": False, "mode": "precomputed"}
    if len(loops) != len(spec.get("loops", [])):
        raise RuntimeError(f"loop_dominance.json lists {len(loops)} loops, validation.toml declares {len(spec.get('loops', []))}")
    pys = []
    for (lab, _), df in zip(sets, dfs):
        v = ld.values_from_frame(model, df)
        ls = ld.link_scores(model, v)
        an = ld.analyze(model, v)
        by_cycle = {tuple(l["py"]): l["id"] for l in an["loops"]}
        rel = {lid: an["relative_scores"][lid] for lid in by_cycle.values()}
        pys.append((lab, {"links": {f"{x}>{z}": (None if a is None else np.asarray(a, float)) for (x, z), a in ls.items()},
                          "rel": {tuple_: rel[lid] for tuple_, lid in by_cycle.items()}}))
    keys = [tuple(lp) for lp in loops]
    base_job = {"engine": engine, "eqs": eqs, "ltm": ltm, "names": ir["names"], "loops": loops, "dt": spec["model"]["time_step"]}
    js_e2e = _node(dict(base_job, runs=[{"params": p} for _, p in sets]))
    values = []
    for df in dfs:
        values.append({"values": {"time": [float(t) for t in df.index],
                                  "series": {c: [float(x) for x in df[c]] for c in df.columns}}})
    js_impl = _node(dict(base_job, runs=values))
    pys_keyed = [(lab, {"links": d["links"], "rel": d["rel"]}) for lab, d in pys]
    e2e = _compare(pys_keyed, js_e2e, keys)
    impl = _compare(pys_keyed, js_impl, keys)
    ok = e2e["complete"] and e2e["max_link"] <= TOL and e2e["max_loop"] <= TOL
    return {"labels": [lab for lab, _ in sets], "n_runs": len(sets), "n_link_series": e2e["n_link"], "n_loop_series": e2e["n_loop"],
            "end_to_end": e2e, "implementation": impl, "tolerance": TOL, "pass": bool(ok), "mode": "live" if ok else "precomputed"}


def js_restricted_dominance(spec, project_dir, stock_name):
    """Customer-restricted (or any stock-restricted) dominance periods at base, computed by the page's code."""
    py_path = spec["model"]["py_path"]
    ir = export_js.load_ir(py_path)
    dom = json.load(open(os.path.join(project_dir, "loop_dominance.json")))
    loops = [lp["py"] for lp in dom["loops"]]
    subset = [i for i, lp in enumerate(dom["loops"]) if stock_name in lp["variables"]]
    job = {"engine": export_js.emit_js(ir), "eqs": export_js.emit_eqs(py_path), "ltm": open(LTM_JS, encoding="utf-8").read(),
           "names": ir["names"], "loops": loops, "dt": spec["model"]["time_step"], "runs": [{"params": {}}],
           "restrict": {"subset": subset, "labels": [lp["name"] for lp in dom["loops"]], "min_length": 1.0}}
    node = shutil.which("node")
    p = subprocess.run([node, RUNNER], input=json.dumps(job), capture_output=True, text=True, timeout=600)
    if p.returncode != 0:
        raise RuntimeError(p.stderr[-800:])
    return json.loads(p.stdout)[0]["dominance"]


def precomputed(project_dir, spec, step):
    """Base-case link and loop scores from loop_detector (PySD run saved every dt), kept at times that are multiples of
    `step` (pass the model's dt to keep every value), for the page when the gate fails."""
    py_path = spec["model"]["py_path"]
    model = ld.parse_model(py_path)
    df = validate.run_batch(py_path, [{"params": {}, "saveper_dt": True}])[0]
    v = ld.values_from_frame(model, df)
    ls = ld.link_scores(model, v)
    an = ld.analyze(model, v)
    by_cycle = {tuple(l["py"]): l["id"] for l in an["loops"]}
    t = v["time"][1:]
    keep = [i for i, x in enumerate(t) if abs(x / step - round(x / step)) < 1e-9]
    fin = lambda a: [None if not math.isfinite(float(a[i])) else float(a[i]) for i in keep]  # noqa: E731
    return {"time": [float(t[i]) for i in keep],
            "links": {f"{x}>{z}": (None if a is None else fin(a)) for (x, z), a in ls.items()},
            "rel": [fin(np.asarray(an["relative_scores"][by_cycle[tuple(lp)]], float)) for lp in loops_of(project_dir)]}


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    spec = validate.load_spec(os.path.join(argv[1], "validation.toml"))
    rep = run_ltm_gate(spec, argv[1])
    print(json.dumps(rep, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
