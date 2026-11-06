"""Project checks for car-dealership-profit, required at gate 7 (gate 1 and gate 4 decisions). Run AFTER engine/validate.py:

    .venv/bin/python -I projects/car-dealership-profit/checks.py

1. P&L identity: net profit = total gross - commissions - marketing spend - F and I programme spend - technician payroll
   - wholesale loss - fixed overhead - floorplan interest at every step (base, fastest corner, and a shocked scenario).
2. Equity identity: Cash + Inventory at Cost - Floorplan Debt - Cumulative Net Profit stays equal to its opening value.
3. Oracle: the PySD model equals the independent Euler mirror (settle.py, a second implementation of the same
   equations) step for step, in the base and in the shocked scenario.

Writes checks_results.json (with the sha256 of every file the checks read), appends its numbers to validation_report.md
(validate.py rewrites that file on every run, so the order matters) and exits 0 only if all checks pass. On failure it marks
the report WITHHELD and deletes any results validate.py released.
"""
import hashlib
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "engine"))
sys.path.insert(0, HERE)
import validate  # noqa: E402
import settle  # noqa: E402

PL_TOL = 1e-6          # max |gap| / max |net profit|
EQ_TOL = 1e-6          # max |drift| / opening gross asset scale (inventory at cost)
ORACLE_TOL = 1e-6      # max |PySD - mirror| / max |mirror|, per series
RELEASE = ("mc_bands.csv", "policy_results.csv", "loop_dominance.json")
SHOCKED = {"margin shock size": 0.3, "rate shock size": 0.03, "demand shock size": 0.2, "target used days supply": 78.0,
           "allocation response strength": 0.4, "retention loss when overloaded": 0.3, "attrition rate": 0.35,
           "F and I programme spend": 10000.0, "marketing spend": 35000.0, "technician target": 29.7}
PL_TERMS = ["total gross", "commissions", "marketing spend", "F and I programme spend", "technician payroll", "wholesale loss",
            "fixed overhead", "floorplan interest"]
ORACLE_SERIES = ["net profit", "Cumulative Net Profit", "Cash", "New Inventory", "Used Frontline Inventory", "Owners",
                 "Service Customers", "Floorplan Debt", "Technicians", "Prospects", "used price discount", "absorption rate"]


def _cases(spec):
    return {"base": validate.base_params(spec), "corner": validate.corner_params(spec),
            "shocked": dict(validate.base_params(spec), **SHOCKED)}


def _runs(spec, cases):
    m = spec["model"]
    kw = dict(final_time=m["final_time"], time_step=m["time_step"], saveper_dt=True)
    dfs = validate.run_batch(m["py_path"], [dict(params=p, **kw) for p in cases.values()])
    return dict(zip(cases, dfs)) if len(dfs) == len(cases) else None


def identities(spec, runs, cases):
    pl = {"pass": True, "tolerance": PL_TOL, "cases": {}}
    eq = {"pass": True, "tolerance": EQ_TOL, "cases": {}}
    for name, df in runs.items():
        if df is None:
            pl["pass"] = eq["pass"] = False
            pl["cases"][name] = eq["cases"][name] = {"error": "run failed"}
            continue
        col = lambda n: np.asarray(df[n], float)  # noqa: E731
        p = cases[name]
        # marketing spend and F and I programme spend are constants, so use the case's own values
        rhs = col("total gross") - col("commissions") - p["marketing spend"] - p["F and I programme spend"] - col("technician payroll") \
            - col("wholesale loss") - p["fixed overhead"] - col("floorplan interest")
        gap = float(np.max(np.abs(col("net profit") - rhs)))
        rel = gap / max(float(np.max(np.abs(col("net profit")))), 1e-300)
        pl["cases"][name] = {"max_abs_gap": gap, "rel_gap": rel, "pass": rel < PL_TOL}
        pl["pass"] &= rel < PL_TOL
        eqty = col("Cash") + col("Inventory at Cost") - col("Floorplan Debt") - col("Cumulative Net Profit")
        drift = float(np.max(np.abs(eqty - eqty[0])))
        scale = float(np.max(np.abs(col("Inventory at Cost"))))
        eq["cases"][name] = {"max_abs_drift": drift, "rel_drift": drift / scale, "opening_equity": float(eqty[0]), "pass": drift / scale < EQ_TOL}
        eq["pass"] &= drift / scale < EQ_TOL
    return pl, eq


def oracle(spec, runs):
    init = json.load(open(os.path.join(HERE, "settled_initial.json")))["initial"]
    dt = spec["model"]["time_step"]
    out = {"pass": True, "tolerance": ORACLE_TOL, "cases": {}}
    for name in ("base", "shocked"):
        df = runs.get(name)
        if df is None:
            out["pass"] = False
            out["cases"][name] = {"error": "run failed"}
            continue
        V = settle.base_values(SHOCKED if name == "shocked" else None)
        V["reference new sales"], V["reference used sales"], V["initial cash"] = init["reference new sales"], init["reference used sales"], init["initial cash"]
        S = settle.initial_stocks(V, init)
        _, tr, _ = settle.run(V, S, spec["model"]["final_time"], dt, record=ORACLE_SERIES)
        worst = {}
        for k in ORACLE_SERIES:
            a, b = np.asarray(df[k], float), np.asarray(tr[k], float)
            worst[k] = float(np.max(np.abs(a - b)) / max(float(np.max(np.abs(b))), 1e-300)) if a.size == b.size else float("inf")
        w = max(worst.values())
        out["cases"][name] = {"max_rel_diff": w, "worst_series": max(worst, key=worst.get), "pass": w < ORACLE_TOL}
        out["pass"] &= w < ORACLE_TOL
    return out


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def inputs(spec):
    own = [os.path.abspath(__file__), os.path.join(HERE, "validation.toml"), spec["model"]["mdl_path"], spec["model"]["py_path"],
           os.path.join(HERE, "model_spec.py"), os.path.join(HERE, "settle.py"), os.path.join(HERE, "settled_initial.json")]
    return {os.path.relpath(p, HERE).replace(os.sep, "/"): _sha(p) for p in own}, {}


def main():
    spec = validate.load_spec(os.path.join(HERE, "validation.toml"))
    own, other = inputs(spec)
    report = os.path.join(HERE, "validation_report.md")
    if not os.path.exists(report):
        print("validation_report.md not found: run engine/validate.py first (checks.py appends to its report)")
        return 1
    cases = _cases(spec)
    runs = _runs(spec, cases)
    if runs is None:
        print("expected one run per case")
        return 1
    pl, eq = identities(spec, runs, cases)
    R = {"pl_identity": pl, "equity_identity": eq, "oracle_vs_mirror": oracle(spec, runs)}
    R["all_pass"] = all(v["pass"] for v in R.values() if isinstance(v, dict))
    R["inputs"], R["external_inputs"] = own, other
    json.dump(R, open(os.path.join(HERE, "checks_results.json"), "w"), indent=1, default=str)
    L = ["", "## Project checks (checks.py, required at gate 7)", "",
         f"Overall: **{'PASS' if R['all_pass'] else 'FAIL'}**. Numbers copied from `checks_results.json` by the script.", "",
         "| Check | Case | Result | Key number |", "|---|---|---|---|"]
    for k, c in pl["cases"].items():
        L.append(f"| P&L identity | {k} | {'PASS' if c.get('pass') else 'FAIL'} | " + (f"max gap {c['max_abs_gap']:.3g} USD/Month, relative {c['rel_gap']:.3g} (limit {PL_TOL:g}) |" if "rel_gap" in c else c.get("error", "") + " |"))
    for k, c in eq["cases"].items():
        L.append(f"| Equity identity | {k} | {'PASS' if c.get('pass') else 'FAIL'} | " + (f"max drift {c['max_abs_drift']:.3g} USD, relative to inventory at cost {c['rel_drift']:.3g} (limit {EQ_TOL:g}) |" if "rel_drift" in c else c.get("error", "") + " |"))
    for k, c in R["oracle_vs_mirror"]["cases"].items():
        L.append(f"| PySD vs independent mirror ({len(ORACLE_SERIES)} series) | {k} | {'PASS' if c.get('pass') else 'FAIL'} | " + (f"max relative difference {c['max_rel_diff']:.3g}, worst series {c['worst_series']} (limit {ORACLE_TOL:g}) |" if "max_rel_diff" in c else c.get("error", "") + " |"))
    if not R["all_pass"]:
        removed = [f for f in RELEASE if os.path.exists(os.path.join(HERE, f))]
        for f in removed:
            os.remove(os.path.join(HERE, f))
        L += ["", "**WITHHELD**: a required project check failed. Released results removed: " + (", ".join(removed) if removed else "none")
              + ". Fix the model or spec and rerun validate.py, then checks.py."]
    open(report, "a").write("\n".join(L) + "\n")
    print("\n".join(L))
    return 0 if R["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
