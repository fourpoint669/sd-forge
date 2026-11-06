"""Parity gate for sd-explorer: the JS engine must reproduce PySD on the validated model.

Usage:  python -I engine/explorer_parity.py projects/<model>/validation.toml

Settings: base; >= 20 seeded uniform-random draws inside every parameter's validated [low, high]; all-low and all-high
corners; every [[policies]] scenario (validate.apply_changes); a 'domain low' corner (each sampled parameter at its
domain minimum, reachable with the page's extend toggle; gated when PySD completes it, reported when PySD errors).
Every column PySD returns (stocks, flows, auxiliaries, constants) and the saved time index are compared.

Metric (fixed at approval; never loosened to make a run pass), per series with S = max_t |py|:
  A = max_t |js - py| / S                               (all-zero series: must match exactly)
  B = max |js - py| / |py| over points with |py| >= 1e-6 * S
Pass iff A <= 1e-9 and B <= 1e-9 for every series of every gated run. Non-finite values must match in place.
"""
import json
import math
import os
import shutil
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import validate  # noqa: E402  (read-only dependency)

TOL = 1e-9
POINTWISE_FLOOR = 1e-6
N_RANDOM = 25
SEED = 20261029
RUNNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "explorer_node_runner.js")


def parity_metrics(py, js):
    """{'scale': A, 'pointwise': B} for one series (see module docstring)."""
    py, js = np.asarray(py, dtype=float), np.asarray(js, dtype=float)
    if py.shape != js.shape or py.size == 0:          # an empty series is not a comparison
        return {"scale": math.inf, "pointwise": math.inf}
    if py.shape != js.shape:
        return {"scale": math.inf, "pointwise": math.inf}
    fin = np.isfinite(py)
    same_nonfinite = np.array_equal(np.isnan(py), np.isnan(js)) and np.array_equal(
        np.where(np.isinf(py), py, 0), np.where(np.isinf(js), js, 0))
    if not same_nonfinite or not np.all(np.isfinite(js[fin])):
        return {"scale": math.inf, "pointwise": math.inf}
    if not fin.any():
        return {"scale": 0.0, "pointwise": 0.0}
    p, j = py[fin], js[fin]
    diff = np.abs(j - p)
    s = float(np.max(np.abs(p)))
    if s == 0.0:
        a = 0.0 if float(np.max(diff)) == 0.0 else math.inf
        return {"scale": a, "pointwise": a}
    keep = np.abs(p) >= POINTWISE_FLOOR * s
    b = float(np.max(diff[keep] / np.abs(p[keep]))) if keep.any() else 0.0
    return {"scale": float(np.max(diff)) / s, "pointwise": b}


def lever_settings(spec, n_random=N_RANDOM, seed=SEED):
    """[(label, params)] in a fixed order; params are full parameter dicts (real names)."""
    base = validate.base_params(spec)
    pars = spec["parameters"]
    varied = sorted(k for k, v in pars.items() if v["high"] > v["low"])
    rng = np.random.default_rng(seed)
    out = [("base", dict(base))]
    for i in range(n_random):
        p = dict(base)
        for k in varied:
            p[k] = float(rng.uniform(pars[k]["low"], pars[k]["high"]))
        out.append((f"random {i + 1}", p))
    out.append(("corner low", {**base, **{k: float(pars[k]["low"]) for k in varied}}))
    out.append(("corner high", {**base, **{k: float(pars[k]["high"]) for k in varied}}))
    for pol in spec.get("policies", []):
        out.append((f"policy: {pol['name']}", validate.apply_changes(spec, base, pol.get("changes"))))
    dom = dict(base)
    for k in varied:
        lo = pars[k].get("domain", [-math.inf, math.inf])[0]
        dom[k] = float(lo) if math.isfinite(lo) else float(pars[k]["low"])
    out.append(("domain low", dom))
    return out


def node_run(engine_js, runs, metrics_js=None, metric_defs=()):
    """Run the engine under node; returns one dict per run (time, series[, metrics]) or {'error': ...}."""
    node = shutil.which("node")
    if not node:
        raise RuntimeError("node not found on PATH: the parity gate cannot run (it never skips)")
    p = subprocess.run([node, RUNNER], input=json.dumps({"engine": engine_js, "runs": runs, "metrics": metrics_js,
                                       "metric_defs": list(metric_defs)}),
                       capture_output=True, text=True, timeout=600)
    if p.returncode != 0:
        raise RuntimeError("node runner failed: " + p.stderr.strip()[-500:])
    dec = lambda x: float(x) if isinstance(x, str) else x  # noqa: E731
    out = json.loads(p.stdout)
    for r in out:
        if "time" in r:
            r["time"] = [dec(x) for x in r["time"]]
            r["series"] = {k: [dec(x) for x in v] for k, v in r["series"].items()}
            if "metrics" in r:
                r["metrics"] = {k: dec(v) for k, v in r["metrics"].items()}
    return out


def metric_rel(py, js):
    """Relative difference of one headline value (both non-finite and equal -> 0; py == 0 -> exact match)."""
    if not (math.isfinite(py) and math.isfinite(js)):
        return 0.0 if (py == js or (math.isnan(py) and math.isnan(js))) else math.inf
    if py == 0.0:
        return 0.0 if js == 0.0 else math.inf
    return abs(js - py) / abs(py)


def run_parity(spec, engine_js, n_random=N_RANDOM, seed=SEED, metrics_js=None):
    """Compare JS with PySD on lever_settings(spec). Returns the report dict (key 'pass').
    With metrics_js (the page's SDMetrics script), every [montecarlo] metric of every run is also compared with
    validate.stat on the PySD run (same tolerance), reported under 'headline'."""
    settings = lever_settings(spec, n_random, seed)
    defs = spec.get("montecarlo", {}).get("metrics", [])
    py_runs = validate.run_batch(spec["model"]["py_path"], [{"params": p} for _, p in settings])
    js_runs = node_run(engine_js, [{"params": p} for _, p in settings], metrics_js, defs)
    rep = {"metric": "A = max|js-py|/S, S = max|py| per series; B = max|js-py|/|py| where |py| >= 1e-6*S",
           "tolerance": TOL, "pointwise_floor": POINTWISE_FLOOR, "seed": seed, "n_random": n_random,
           "n_runs": 0, "n_series": 0, "max_scale_rel": 0.0, "max_pointwise_rel": 0.0,
           "worst_scale": None, "worst_pointwise": None, "missing_columns": [], "errors": [],
           "reported_only": []}
    missing = set()
    head = {"n_values": 0, "max_rel": 0.0, "worst": None}
    # every requested setting must come back from both sides: zip() would silently drop the missing ones
    if len(js_runs) != len(settings):
        rep["errors"].append({"run": "all", "error": f"JS runner returned {len(js_runs)} results for {len(settings)} settings"})
    if len(py_runs) != len(settings):
        rep["errors"].append({"run": "all", "error": f"PySD returned {len(py_runs)} results for {len(settings)} settings"})
    # each run, on both sides, must hold exactly the model's saved time grid and every model column (validate.frame_problem;
    # the expectation comes from the model file's controls and components, never from the frames)
    import pandas as pd
    ctl = validate.model_controls(spec["model"]["py_path"])
    grid = validate.expected_times(ctl["initial_time"], ctl["final_time"], ctl["saveper"], ctl["time_step"])
    cols = validate.model_columns(spec["model"]["py_path"])

    def js_frame(jr):
        try:
            return pd.DataFrame({c: np.asarray(v, dtype=float) for c, v in jr["series"].items()},
                                index=np.asarray(jr["time"], dtype=float))
        except (KeyError, ValueError, TypeError):
            return None
    for (label, _), df, jr in zip(settings, py_runs, js_runs):
        prob = validate.frame_problem(df, grid, cols) if df is not None else None
        if prob:
            rep["errors"].append({"run": label, "error": f"PySD frame incomplete: {prob}"})
            continue
        if df is not None and "error" not in jr:
            prob = validate.frame_problem(js_frame(jr), grid, cols)
            if prob:
                rep["errors"].append({"run": label, "error": f"JS run incomplete: {prob}"})
                continue
        if df is None:
            if label == "domain low":
                rep["reported_only"].append({"run": label, "note": "PySD did not complete this run; not gated"})
                continue
            rep["errors"].append({"run": label, "error": "PySD run failed"})
            continue
        if "error" in jr:
            rep["errors"].append({"run": label, "error": "JS: " + jr["error"]})
            continue
        rep["n_runs"] += 1
        pairs = [("time", np.asarray(df.index, dtype=float), np.asarray(jr["time"], dtype=float))]
        for col in sorted(df.columns):
            if col not in jr["series"]:
                missing.add(col)
                continue
            pairs.append((col, df[col].to_numpy(dtype=float), np.asarray(jr["series"][col], dtype=float)))
        if metrics_js is not None:
            for d in defs:
                r = metric_rel(validate.stat(df[d["var"]], df.index, d), jr["metrics"][d["name"]])
                head["n_values"] += 1
                if r >= head["max_rel"]:
                    head["max_rel"], head["worst"] = r, {"run": label, "metric": d["name"]}
        for col, py, js in pairs:
            m = parity_metrics(py, js)
            rep["n_series"] += 1
            if m["scale"] >= rep["max_scale_rel"]:
                rep["max_scale_rel"], rep["worst_scale"] = m["scale"], {"run": label, "series": col}
            if m["pointwise"] >= rep["max_pointwise_rel"]:
                rep["max_pointwise_rel"], rep["worst_pointwise"] = m["pointwise"], {"run": label, "series": col}
    rep["missing_columns"] = sorted(missing)
    compared_all = rep["n_runs"] + len(rep["reported_only"]) == len(settings)
    rep["pass"] = bool(not rep["errors"] and not missing and rep["n_runs"] > 0 and n_random >= 1 and compared_all
                       and rep["max_scale_rel"] <= TOL and rep["max_pointwise_rel"] <= TOL)
    if metrics_js is not None:
        rep["headline"] = head
        rep["pass"] = rep["pass"] and head["n_values"] > 0 and head["max_rel"] <= TOL
    return rep


def main(argv):
    import export_js
    if len(argv) != 2:
        print(__doc__)
        return 2
    spec = validate.load_spec(argv[1])
    rep = run_parity(spec, export_js.emit_js(export_js.load_ir(spec["model"]["py_path"])))
    print(json.dumps(rep, indent=1))
    return 0 if rep["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
