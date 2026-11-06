"""Project checks for saas-churn-vs-winrate, required at gate 7 (gate 5 decision). Run AFTER engine/validate.py:

    .venv/bin/python -I projects/saas-churn-vs-winrate/checks.py

1. Regression: with every new mechanism switched off, Customers reproduces projects/bass-b2b-adoption step for step.
2. ARR identity: with expansion off, ARR = Customers x new customer ACV at every step (base and fastest corner).

Writes checks_results.json (with the sha256 of every file the checks read: this script, the spec and model files of
this project, and the bass-b2b-adoption spec and model the regression runs), appends its numbers to validation_report.md (validate.py rewrites that file on every run,
so the order matters) and exits 0 only if both checks pass. On failure it marks the report WITHHELD and deletes any
results validate.py released, so summary.md, the fan chart and any explorer stay withheld.
"""
import hashlib
import json
import os
import sys
import tomllib

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "engine"))
import validate  # noqa: E402

REG_TOL = 1e-9        # max |difference| / max(example Customers)
ID_TOL = 1e-6         # max |ARR - Customers x ACV| / max(ARR)
RELEASE = ("mc_bands.csv", "policy_results.csv", "loop_dominance.json")
EXAMPLE = os.path.join(ROOT, "projects", "bass-b2b-adoption")
# example parameter name -> this model's name (same meaning)
RENAME = {"win rate": "base win rate", "annual logo churn rate": "base annual churn rate", "total market": "initial total market"}
OFF = {"total programme budget": 0, "expansion lift at full CS effect": 0, "sales capacity growth rate": 0,
       "negative word of mouth multiplier": 0, "base net expansion rate": 0, "market growth rate": 0,
       "initial sales capacity": 1e9}


def regression(spec):
    ex = validate.load_spec(os.path.join(EXAMPLE, "validation.toml"))
    shared = {RENAME.get(k, k): v["base"] for k, v in ex["parameters"].items()}
    params = dict(validate.base_params(spec), **shared, **OFF)
    m = spec["model"]
    kw = dict(final_time=m["final_time"], time_step=m["time_step"], saveper_dt=True)
    ra = validate.run_batch(ex["model"]["py_path"], [dict(params=validate.base_params(ex), **kw)])
    rb = validate.run_batch(m["py_path"], [dict(params=params, **kw)])
    if len(ra) != 1 or len(rb) != 1:
        return {"pass": False, "error": f"expected one run of each model, got {len(ra)} and {len(rb)}"}
    a, b = ra[0], rb[0]
    if a is None or b is None:
        return {"pass": False, "error": "a run failed", "worker_errors": str(validate.run_batch.last_errors)[:300]}
    if not np.array_equal(np.asarray(a.index, float), np.asarray(b.index, float)):
        return {"pass": False, "error": "time grids differ"}
    ya, yb = np.asarray(a["Customers"], float), np.asarray(b["Customers"], float)
    diff = float(np.max(np.abs(ya - yb)))
    rel = diff / float(np.max(np.abs(ya)))
    return {"pass": rel <= REG_TOL, "max_abs_diff": diff, "rel_diff": rel, "tolerance": REG_TOL, "steps": int(ya.size),
            "dt": m["time_step"], "months": m["final_time"], "settings": OFF, "shared_params_from_example": shared}


def identity(spec):
    m = spec["model"]
    off = {"base net expansion rate": 0, "expansion lift at full CS effect": 0}
    cases = {"base": dict(validate.base_params(spec), **off), "corner": dict(validate.corner_params(spec), **off)}
    kw = dict(final_time=m["final_time"], time_step=m["time_step"], saveper_dt=True)
    dfs = validate.run_batch(m["py_path"], [dict(params=p, **kw) for p in cases.values()])
    out = {"pass": len(dfs) == len(cases), "tolerance": ID_TOL, "settings": off, "cases": {}}
    if len(dfs) != len(cases):       # every case must run: zip() below would silently drop the missing ones
        out["error"] = f"expected {len(cases)} runs ({', '.join(cases)}), got {len(dfs)}"
    for (name, p), df in zip(cases.items(), dfs):
        if df is None:
            out["pass"] = False
            out["cases"][name] = {"error": "run failed"}
            continue
        arr = np.asarray(df["ARR"], float)
        gap = float(np.max(np.abs(arr - np.asarray(df["Customers"], float) * p["new customer ACV"])))
        rel = gap / max(float(np.max(np.abs(arr))), 1e-300)
        out["cases"][name] = {"max_abs_gap": gap, "rel_gap": rel, "pass": rel < ID_TOL}
        out["pass"] &= rel < ID_TOL
    return out


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def inputs(spec):
    """sha256 of every file these checks read, recorded so a later tool can tell whether they changed (record-only).
    Project files are keyed relative to this folder; the other project's files relative to the repository root."""
    ex = validate.load_spec(os.path.join(EXAMPLE, "validation.toml"))
    own = [os.path.abspath(__file__), os.path.join(HERE, "validation.toml"), spec["model"]["mdl_path"], spec["model"]["py_path"]]
    other = [os.path.join(EXAMPLE, "validation.toml"), ex["model"]["mdl_path"], ex["model"]["py_path"]]
    rel = lambda p, base: os.path.relpath(p, base).replace(os.sep, "/")  # noqa: E731
    return ({rel(p, HERE): _sha(p) for p in own}, {rel(p, ROOT): _sha(p) for p in other})


def main():
    spec = validate.load_spec(os.path.join(HERE, "validation.toml"))
    own, other = inputs(spec)
    report = os.path.join(HERE, "validation_report.md")
    if not os.path.exists(report):
        print("validation_report.md not found: run engine/validate.py first (checks.py appends to its report)")
        return 1
    R = {"regression_vs_bass_b2b_adoption": regression(spec), "arr_identity": identity(spec)}
    R["all_pass"] = all(v["pass"] for v in R.values() if isinstance(v, dict))
    R["inputs"], R["external_inputs"] = own, other
    json.dump(R, open(os.path.join(HERE, "checks_results.json"), "w"), indent=1, default=str)
    g, i = R["regression_vs_bass_b2b_adoption"], R["arr_identity"]
    L = ["", "## Project checks (checks.py, required at gate 7)", "",
         f"Overall: **{'PASS' if R['all_pass'] else 'FAIL'}**. Numbers copied from `checks_results.json` by the script.", "",
         "| Check | Result | Key number |", "|---|---|---|"]
    L.append(f"| Regression vs bass-b2b-adoption (Customers, {g.get('steps', '?')} steps) | {'PASS' if g['pass'] else 'FAIL'} | "
             + (f"max abs diff {g['max_abs_diff']:.3g} Firm, relative {g['rel_diff']:.3g} (limit {REG_TOL:g})" if "rel_diff" in g else g.get("error", "")) + " |")
    for k, c in i["cases"].items():
        L.append(f"| ARR identity ({k}) | {'PASS' if c.get('pass') else 'FAIL'} | "
                 + (f"max gap {c['max_abs_gap']:.3g} USD/Year, relative {c['rel_gap']:.3g} (limit {ID_TOL:g})" if "rel_gap" in c else c.get("error", "")) + " |")
    if not R["all_pass"]:
        removed = [f for f in RELEASE if os.path.exists(os.path.join(HERE, f))]
        for f in removed:
            os.remove(os.path.join(HERE, f))
        L += ["", "**WITHHELD**: a required project check failed. Released results removed: "
              + (", ".join(removed) if removed else "none") + ". Fix the model or spec and rerun validate.py, then checks.py."]
    open(report, "a").write("\n".join(L) + "\n")
    print("\n".join(L))
    return 0 if R["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
