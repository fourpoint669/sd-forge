"""Gate 8 analysis on the validated model (run only after validate.py and checks.py exit 0):

    .venv/bin/python -I projects/car-dealership-profit/gate8_analysis.py

Re-runs every [[policies]] scenario on the SAME Latin hypercube samples validate.py used (same n and seed), so per-sample
comparisons against the baseline store are possible; checks that the cumulative-profit percentiles reproduce
policy_results.csv; then computes, per scenario and sample:
  - gain vs the baseline store in cumulative net profit at months 60, 120 and 180, and in discounted cash flow at month 120;
  - resilience: lowest monthly net profit inside months 0-60 and inside the shock window, share of months 0-60 with a loss,
    lowest absorption rate inside the window;
  - probability each scenario beats the baseline, beats each other scenario, and is best;
  - Spearman drivers of each scenario's gain;
and loop dominance on the all-three-shocks scenario (the base run is at rest, so its dominance timeline is empty).
Writes gate8_results.json, scenario_gains.csv, resilience.csv and loop_dominance_shock.json.
"""
import csv
import hashlib
import json
import os
import sys

import numpy as np
from scipy.stats import spearmanr

HERE = os.path.dirname(os.path.abspath(__file__))
# generator declaration (read by engine/explorer_release.py): files this script writes, and result files it reads besides
# itself, validation.toml and the model.
WRITES = ("scenario_gains.csv", "resilience.csv", "loop_dominance_shock.json")
READS = ("policy_results.csv", "loop_dominance.json", "declared_loops_draft.json")
sys.path.insert(0, os.path.join(HERE, "..", "..", "engine"))
import validate  # noqa: E402
import loop_detector as ld  # noqa: E402

COLS = ["Cumulative Net Profit", "Cumulative Discounted Cash Flow", "net profit", "absorption rate", "Cash"]
Q = [5, 25, 50, 75, 95]
BASE = "baseline store (no lever change)"
SHOCK_ALL = "B all three shocks together, 12 months"
LEVER_COST_60 = 10000.0 * 60       # lens A scenarios are sized to about $10k a month of added cost


def at(df, col, t):
    return float(np.interp(t, np.asarray(df.index, float), np.asarray(df[col], float)))


def pct(v):
    v = np.asarray(v, float)
    v = v[np.isfinite(v)]
    return {f"P{q}": float(np.percentile(v, q)) for q in Q} if v.size else {}


def window_min(df, col, lo, hi):
    t = np.asarray(df.index, float)
    y = np.asarray(df[col], float)
    k = (t >= lo) & (t <= hi)
    return float(y[k].min())


def family(vs):
    t = set(vs)
    if "utilisation" in t: return "service congestion [A]"
    if "allocation response" in t: return "allocation response [C]"
    if "Technicians" in t: return "technician adjustment"
    if "Lessees Early" in t: return "lease echo"
    if "wholesale exits" in t: return "wholesale exit"
    if "used price discount" in t and "Owners" not in t: return "used discounting"
    if "service ratio" in t: return "service loyalty"
    if "repeat to store" in t: return "repeat purchase"
    if t & {"New Inventory", "New Vehicles On Order"} and "Prospects" not in t: return "new-vehicle ordering"
    if "Reconditioning Pipeline" in t and "Prospects" not in t: return "used sourcing"
    if "Prospects" in t: return "prospect drain"
    return "first-order adjustment"


def main():
    spec = validate.load_spec(os.path.join(HERE, "validation.toml"))
    m, mc = spec["model"], spec["montecarlo"]
    n, seed = mc["n"], mc["seed"]
    names, samples = validate.lhs_samples(spec, n, seed)
    kw = dict(final_time=m["final_time"], time_step=m["time_step"], saveper=m.get("saveper", 1), return_columns=COLS)
    pols = spec["policies"]
    runs, plist = [], []
    for p in pols:
        for s in samples:
            q = validate.apply_changes(spec, s, p.get("changes"))
            runs.append(dict(params=q, **kw))
            plist.append(q)
    dfs = validate.run_batch(m["py_path"], runs)
    if any(d is None for d in dfs):
        raise SystemExit(f"{sum(d is None for d in dfs)} runs failed: {validate.run_batch.last_errors}")
    per = {p["name"]: dfs[i * n:(i + 1) * n] for i, p in enumerate(pols)}
    par = {p["name"]: plist[i * n:(i + 1) * n] for i, p in enumerate(pols)}

    met = {}
    for name, ds in per.items():
        wl = [(q["shock start month"], q["shock start month"] + q["shock duration"]) for q in par[name]]
        met[name] = {
            "cp60": np.array([at(d, "Cumulative Net Profit", 60) for d in ds]),
            "cp120": np.array([at(d, "Cumulative Net Profit", 120) for d in ds]),
            "cp180": np.array([at(d, "Cumulative Net Profit", 180) for d in ds]),
            "dcf120": np.array([at(d, "Cumulative Discounted Cash Flow", 120) for d in ds]),
            "cash60": np.array([at(d, "Cash", 60) for d in ds]),
            "min_np_0_60": np.array([window_min(d, "net profit", 0, 60) for d in ds]),
            "min_np_window": np.array([window_min(d, "net profit", lo, hi) for d, (lo, hi) in zip(ds, wl)]),
            "min_abs_window": np.array([window_min(d, "absorption rate", lo, hi) for d, (lo, hi) in zip(ds, wl)]),
            "loss_share_0_60": np.array([float(np.mean(np.asarray(d["net profit"])[:61] < 0)) for d in ds]),
        }
    # consistency with validate.py's policy_results.csv (same samples, same seed)
    ref = {r["scenario"]: r for r in csv.DictReader(open(os.path.join(HERE, "policy_results.csv")))}
    cons = {}
    for name in per:
        for q in (5, 50, 95):
            a, b = float(np.percentile(met[name]["cp60"], q)), float(ref[name][f"P{q}"])
            cons[f"{name} P{q}"] = abs(a - b) / max(abs(b), 1.0)
    base = met[BASE]
    scen = {}
    for name in per:
        d = {}
        for key in ("cp60", "cp120", "cp180", "dcf120", "cash60"):
            g = met[name][key] - base[key]
            d[f"gain_{key}"] = pct(g)
            d[f"p_gain_{key}_positive"] = float(np.mean(g > 0))
        for key in ("min_np_0_60", "min_np_window", "min_abs_window", "loss_share_0_60"):
            d[key] = pct(met[name][key])
            d[f"delta_{key}"] = pct(met[name][key] - base[key])
        d["cp60"] = pct(met[name]["cp60"])
        d["dcf120"] = pct(met[name]["dcf120"])
        d["cp60_gain_per_dollar_of_added_cost"] = d["gain_cp60"]["P50"] / LEVER_COST_60 if name.startswith("A ") else None
        scen[name] = d
    nm = list(per)
    X = np.vstack([met[k]["cp60"] for k in nm])
    best = np.argmax(X, axis=0)
    p_best = {k: float(np.mean(best == i)) for i, k in enumerate(nm)}
    pairwise = {a: {b: float(np.mean(met[a]["cp60"] > met[b]["cp60"])) for b in nm if b != a} for a in nm}
    # Spearman drivers of each scenario's gain in cumulative profit at month 60
    P = np.array([[s[k] for k in names] for s in samples])
    drivers = {}
    for name in nm:
        if name == BASE:
            continue
        g = met[name]["cp60"] - base["cp60"]
        if np.ptp(g) == 0:
            drivers[name] = []
            continue
        rho = [(k, float(spearmanr(P[:, j], g)[0])) for j, k in enumerate(names)]
        drivers[name] = sorted(rho, key=lambda x: -abs(x[1]))[:5]
    # loop dominance on the all-three-shocks scenario at the base parameters
    model = ld.parse_model(m["py_path"])
    sp = next(p for p in pols if p["name"] == SHOCK_ALL)
    sh = validate.apply_changes(spec, validate.base_params(spec), sp["changes"])
    full = validate.run_batch(m["py_path"], [dict(params=sh, final_time=m["final_time"], time_step=m["time_step"], saveper_dt=True)])[0]
    la = ld.analyze(model, ld.values_from_frame(model, full))
    decl = {d["id"]: d for d in json.load(open(os.path.join(HERE, "declared_loops_draft.json")))}
    _, nmap = validate.match_loops(la["loops"], spec["loops"])
    byid = {d["id"]: d for d in la["loops"]}
    top = sorted(la["loops"], key=lambda d: -(d["mean_abs_relative_score"] or 0))[:12]
    dom = ld.merge_short_periods(la["dominance"], spec.get("dominance_min_period", 1.0))
    shock_out = {
        "scenario": SHOCK_ALL, "window": [sh["shock start month"], sh["shock start month"] + sh["shock duration"]],
        "dominance": [{"start": p["start"], "end": p["end"], "loop": nmap.get(p["loop"]) if p["loop"] is not None else None,
                       "family": family(byid[p["loop"]]["variables"]) if p["loop"] is not None else None,
                       "mean_relative_score": p["mean_relative_score"]} for p in dom],
        "top_loops": [{"name": nmap.get(d["id"]), "polarity": d["polarity"], "family": family(d["variables"]),
                       "mean_abs_relative_score": d["mean_abs_relative_score"], "max_abs_relative_score": d["max_abs_relative_score"],
                       "variables": d["variables"]} for d in top]}
    json.dump(shock_out, open(os.path.join(HERE, "loop_dominance_shock.json"), "w"), indent=1)
    with open(os.path.join(HERE, "scenario_gains.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["scenario", "metric"] + [f"P{q}" for q in Q] + ["p_gain_positive"])
        for name, d in scen.items():
            for key in ("cp60", "cp120", "cp180", "dcf120", "cash60"):
                if key in ("cp60", "cp120", "cp180", "dcf120", "cash60"):
                    g = d[f"gain_{key}"]
                    w.writerow([name, f"gain_{key}"] + [g.get(f"P{q}") for q in Q] + [d[f"p_gain_{key}_positive"]])
    with open(os.path.join(HERE, "resilience.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["scenario", "metric"] + [f"P{q}" for q in Q])
        for name, d in scen.items():
            for key in ("min_np_0_60", "min_np_window", "min_abs_window", "loss_share_0_60"):
                w.writerow([name, key] + [d[key].get(f"P{q}") for q in Q])
    R = {"n": n, "seed": seed, "consistency_with_policy_results_max_rel": max(cons.values()), "scenarios": scen,
         "p_best_cp60": p_best, "pairwise_p_row_beats_col_cp60": pairwise, "drivers_spearman_gain_cp60": drivers,
         "baseline": {k: pct(base[k]) for k in base}, "lens_a_cost_over_60_months": LEVER_COST_60, "loop_dominance_shock_file": "loop_dominance_shock.json"}
    written = list(WRITES)
    read = [os.path.basename(__file__), "validation.toml", spec["model"]["mdl"], spec["model"]["py"]] + list(READS)
    sha = lambda f: hashlib.sha256(open(os.path.join(HERE, f), "rb").read()).hexdigest()  # noqa: E731
    R["output_files"] = {f: sha(f) for f in written}
    R["inputs"] = {f: sha(f) for f in read}
    json.dump(R, open(os.path.join(HERE, "gate8_results.json"), "w"), indent=1)
    print("consistency with policy_results.csv, max relative:", R["consistency_with_policy_results_max_rel"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
