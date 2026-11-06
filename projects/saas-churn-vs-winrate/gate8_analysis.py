"""Gate 8 analysis on the validated model (run only after validate.py and checks.py exit 0):

    .venv/bin/python -I projects/saas-churn-vs-winrate/gate8_analysis.py

Re-runs every [[policies]] scenario on the SAME Latin hypercube samples validate.py used (same n and seed), so
per-sample comparisons are possible; checks that the no-programme and churn-first percentiles reproduce
policy_results.csv; then computes:
  - per-sample gains vs no programme (ARR at month 60, ARR lift per dollar, cumulative revenue net of spend);
  - probability that churn first beats win rate first (ARR m60, also net cumulative revenue m60 and ARR m120);
  - break-even relative cost-effectiveness k: win-rate programme dollars made k times as effective
    (win spend scale / k) until churn first and win rate first give equal ARR at month 60, per sample;
  - order-only comparison: both orders with an equal 30/30-month split (the defined scenarios split 24/36, so
    "churn first" also gives the win-rate programme 12 more months of budget);
  - Spearman drivers of the churn-first minus win-rate-first difference and of the best-policy flip;
  - how often sales capacity binds; loop dominance restricted to loops through Customers (from loop_dominance.json).
Writes gate8_results.json, scenario_bands.csv (ARR and Customers bands per scenario), breakeven_30_30.csv,
breakeven_24_36.csv and order_difference_bands.csv (per-sample ARR difference, win rate first minus churn first, 30/30).
"""
import csv
import hashlib
import json
import math
import os
import sys

import numpy as np
from scipy.stats import spearmanr

HERE = os.path.dirname(os.path.abspath(__file__))
# generator declaration (read by engine/explorer_release.py): the files this script writes and the result files it
# reads, besides itself, validation.toml and the model. gate8_results.json records the sha256 of all of them.
WRITES = ("scenario_bands.csv", "breakeven_30_30.csv", "breakeven_24_36.csv", "order_difference_bands.csv")
READS = ("policy_results.csv", "loop_dominance.json")
sys.path.insert(0, os.path.join(HERE, "..", "..", "engine"))
import validate  # noqa: E402

CF = "churn first (months 0-24 churn, 24-60 win rate)"
WF = "win rate first (months 0-24 win rate, 24-60 churn)"
K_GRID = [2 ** (x / 2) for x in range(-6, 7)]          # 0.125 ... 8, steps of sqrt(2)
COLS = ["ARR", "Customers", "Cumulative Revenue", "Cumulative Programme Spend", "deal closings", "sales capacity"]
Q = [5, 25, 50, 75, 95]


def at(df, col, t):
    return float(np.interp(t, np.asarray(df.index, float), np.asarray(df[col], float)))


def pct(v):
    v = np.asarray(v, float)
    v = v[np.isfinite(v)]
    return {f"P{q}": float(np.percentile(v, q)) for q in Q} if v.size else {}


def main():
    spec = validate.load_spec(os.path.join(HERE, "validation.toml"))
    m, mc = spec["model"], spec["montecarlo"]
    n, seed = mc["n"], mc["seed"]
    names, samples = validate.lhs_samples(spec, n, seed)
    kw = dict(final_time=m["final_time"], time_step=m["time_step"], saveper=m.get("saveper", 1), return_columns=COLS)
    pols = spec["policies"]
    runs = [dict(params=validate.apply_changes(spec, s, p.get("changes")), **kw) for p in pols for s in samples]
    dfs = validate.run_batch(m["py_path"], runs)
    if any(d is None for d in dfs):
        raise SystemExit(f"{sum(d is None for d in dfs)} runs failed: {validate.run_batch.last_errors}")
    per = {p["name"]: dfs[i * n:(i + 1) * n] for i, p in enumerate(pols)}
    budget = np.array([s["total programme budget"] for s in samples])

    met = {}
    for name, ds in per.items():
        met[name] = {
            "arr_m60": np.array([at(d, "ARR", 60) for d in ds]),
            "arr_m120": np.array([at(d, "ARR", 120) for d in ds]),
            "customers_m60": np.array([at(d, "Customers", 60) for d in ds]),
            "cum_revenue_m60": np.array([at(d, "Cumulative Revenue", 60) for d in ds]),
            "spend_m60": np.array([at(d, "Cumulative Programme Spend", 60) for d in ds]),
            # share of months 0-60 in which deal closings run at the sales-capacity limit
            "capacity_bound_share_m0_60": np.array([float(np.mean(np.asarray(d["deal closings"])[:61]
                                                                  >= np.asarray(d["sales capacity"])[:61] * (1 - 1e-9))) for d in ds]),
        }
        met[name]["net_cum_m60"] = met[name]["cum_revenue_m60"] - met[name]["spend_m60"]

    # consistency with validate.py's released policy table (same samples => same percentiles)
    ref = {r["scenario"]: r for r in csv.DictReader(open(os.path.join(HERE, "policy_results.csv")))}
    consistency = {}
    for name in ("no programme", CF):
        mine = np.percentile(met[name]["arr_m60"], [5, 50, 95])
        theirs = np.array([float(ref[name][k]) for k in ("P5", "P50", "P95")])
        consistency[name] = float(np.max(np.abs(mine - theirs) / np.abs(theirs)))
    if max(consistency.values()) > 1e-5:
        raise SystemExit(f"samples do not reproduce policy_results.csv: {consistency}")

    base = met["no programme"]
    funded = [p["name"] for p in pols if p["name"] != "no programme"]
    scen = {}
    for name in funded:
        g = met[name]["arr_m60"] - base["arr_m60"]
        scen[name] = {
            "arr_m60": pct(met[name]["arr_m60"]),
            "arr_gain_vs_none_m60": pct(g),
            "arr_lift_per_dollar": pct(g / budget),                      # USD of ARR (per year) per USD spent
            "net_cum_gain_vs_none_m60": pct(met[name]["net_cum_m60"] - base["cum_revenue_m60"]),
            "p_net_cum_gain_positive": float(np.mean(met[name]["net_cum_m60"] - base["cum_revenue_m60"] > 0)),
            "capacity_bound_share_m0_60": pct(met[name]["capacity_bound_share_m0_60"]),
            "p_capacity_binds_before_m60": float(np.mean(met[name]["capacity_bound_share_m0_60"] > 0)),
        }
    stack = np.vstack([met[f]["arr_m60"] for f in funded])
    best = np.argmax(stack, axis=0)
    p_best = {f: float(np.mean(best == i)) for i, f in enumerate(funded)}
    pairwise = {a: {b: float(np.mean(met[a]["arr_m60"] > met[b]["arr_m60"])) for b in funded if b != a} for a in funded}
    cf_wf = {k: float(np.mean(met[CF][k] > met[WF][k])) for k in ("arr_m60", "arr_m120", "net_cum_m60", "customers_m60")}
    cf_wf_count = {k: int(np.sum(met[CF][k] > met[WF][k])) for k in ("arr_m60", "arr_m120", "net_cum_m60", "customers_m60")}
    d_cf_wf = met[CF]["arr_m60"] - met[WF]["arr_m60"]

    # drivers: Spearman of each sampled parameter with the churn-first minus win-first difference, and with the
    # best-policy margin (best funded scenario's ARR minus the runner-up) sign flips: win rate only vs 50/50
    X = {k: np.array([s[k] for s in samples]) for k in names}
    def sp(y):
        return {k: float(spearmanr(X[k], y).statistic) for k in names}
    drivers = {"cf_minus_wf_arr_m60": sp(d_cf_wf),
               "winonly_minus_5050_arr_m60": sp(met["win rate only"]["arr_m60"] - met["50/50 split"]["arr_m60"]),
               "winonly_minus_churnonly_arr_m60": sp(met["win rate only"]["arr_m60"] - met["churn only"]["arr_m60"])}
    top = sorted(names, key=lambda k: -abs(drivers["cf_minus_wf_arr_m60"][k]))[:4]
    terciles = {}
    for k in top:
        cut = np.percentile(X[k], [100 / 3, 200 / 3])
        bins = np.digitize(X[k], cut)
        terciles[k] = {f"T{b + 1} ({X[k][bins == b].min():.4g}-{X[k][bins == b].max():.4g})":
                       float(np.mean(d_cf_wf[bins == b] > 0)) for b in range(3)}

    # break-even relative cost-effectiveness, for the primary equal split (30/30) and the defined 24/36 variant
    def breakeven_for(switch, label):
        bruns = []
        for k in K_GRID:
            for smp in samples:
                for c1, c2 in ((1, 0), (0, 1)):          # churn first, then win rate first
                    p = dict(smp, **{"phase switch month": switch, "churn share phase 1": c1, "churn share phase 2": c2})
                    p["win spend scale"] = smp["win spend scale"] / k
                    bruns.append(dict(params=p, final_time=m["final_time"], time_step=m["time_step"],
                                      saveper=m.get("saveper", 1), return_columns=["ARR"]))
        bd = validate.run_batch(m["py_path"], bruns)
        if any(d is None for d in bd):
            raise SystemExit(f"break-even runs failed ({label})")
        D = np.zeros((len(K_GRID), n))
        for i in range(len(K_GRID)):
            for j in range(n):
                D[i, j] = at(bd[(i * n + j) * 2], "ARR", 60) - at(bd[(i * n + j) * 2 + 1], "ARR", 60)
        lk = np.log(K_GRID)
        kstar, crossings, kind = np.full(n, np.nan), np.zeros(n, int), np.array([""] * n, dtype=object)
        for j in range(n):
            sg = np.sign(D[:, j])
            idx = np.nonzero(sg[:-1] * sg[1:] < 0)[0]
            crossings[j] = idx.size
            if idx.size:
                i = idx[0]
                t = D[i, j] / (D[i, j] - D[i + 1, j])
                kstar[j] = math.exp(lk[i] + t * (lk[i + 1] - lk[i]))
                kind[j] = "wf_below_cf_above" if D[i, j] < 0 else "cf_below_wf_above"
        up = float(np.mean(np.all(np.diff(D, axis=0) >= -1e-6 * np.abs(D).max(axis=0), axis=0)))
        down = float(np.mean(np.all(np.diff(D, axis=0) <= 1e-6 * np.abs(D).max(axis=0), axis=0)))
        all_pos, all_neg = np.all(D > 0, axis=0), np.all(D < 0, axis=0)
        ks = kstar[np.isfinite(kstar)]
        # samples that never flip on the grid are counted, not given a k* (the direction of the trend varies by sample)
        kfill = np.where(np.isnan(kstar), np.nan, kstar)
        with open(os.path.join(HERE, f"breakeven_{label}.csv"), "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["sample", "kstar", "crossings"] + [f"D_k{k:.3g}" for k in K_GRID])
            for j in range(n):
                w.writerow([j, f"{kfill[j]:.6g}", crossings[j]] + [f"{D[i, j]:.6g}" for i in range(len(K_GRID))])
        return {"split": label, "switch_month": switch,
                "share_difference_nondecreasing_in_k": up, "share_difference_nonincreasing_in_k": down,
                "count_churn_first_ahead_whole_grid": int(all_pos.sum()), "count_win_first_ahead_whole_grid": int(all_neg.sum()),
                "count_crossing": int(ks.size),
                "count_crossing_win_first_below_churn_first_above": int(np.sum(kind == "wf_below_cf_above")),
                "count_crossing_churn_first_below_win_first_above": int(np.sum(kind == "cf_below_wf_above")),
                "kstar_crossing_percentiles": {f"P{q}": float(np.percentile(ks, q)) for q in Q} if ks.size else {},
                "count_kstar_between_0.5_and_2": int(np.sum((ks >= 0.5) & (ks <= 2))),
                "p_churn_first_ahead_by_k": {f"{k:.3g}": float(np.mean(D[i] > 0)) for i, k in enumerate(K_GRID)},
                "count_churn_first_ahead_by_k": {f"{k:.3g}": int(np.sum(D[i] > 0)) for i, k in enumerate(K_GRID)},
                "count_multiple_crossings": int(np.sum(crossings > 1)),
                "kstar_spearman": {k: float(spearmanr(X[k][np.isfinite(kstar)], kstar[np.isfinite(kstar)]).statistic) for k in names}}

    breakeven = {"definition": "k multiplies the win-rate programme's effect per dollar (its win spend scale is divided "
                               "by k) while the churn programme keeps its assumed effect per dollar. So k is the win-rate "
                               "programme's cost-effectiveness relative to the churn programme's, measured against the "
                               "assumptions: k = 1 is exactly as assumed, k = 2 means win-rate dollars work twice as well "
                               "as assumed, k = 0.5 half as well. k* is the k at which churn first and win rate first give "
                               "equal ARR at month 60; k* = 1 would mean the two orders tie at the assumed effectiveness.",
                 "grid": K_GRID,
                 "primary_30_30": breakeven_for(30, "30_30"),
                 "variant_24_36": breakeven_for(24, "24_36")}

    # order-only comparison: equal 30/30 split, so the two orders spend the same months on each programme
    oruns = []
    for s in samples:
        for c1, c2 in ((1, 0), (0, 1)):
            p = dict(s, **{"phase switch month": 30, "churn share phase 1": c1, "churn share phase 2": c2})
            oruns.append(dict(params=p, **kw))
    od = validate.run_batch(m["py_path"], oruns)
    if any(d is None for d in od):
        raise SystemExit("order-only runs failed")
    o_cf, o_wf = od[0::2], od[1::2]
    # per-sample difference over time, win rate first minus churn first (30/30), ARR: bands for gate 9
    tt_o = np.asarray(o_cf[0].index, float)
    dif = np.vstack([np.asarray(w["ARR"], float) - np.asarray(c["ARR"], float) for c, w in zip(o_cf, o_wf)])
    with open(os.path.join(HERE, "order_difference_bands.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        var = "win rate first minus churn first (30/30)|ARR"
        w.writerow(["time"] + [f"{var}|P{q}" for q in Q] + ["share_win_first_ahead"])
        pq = np.percentile(dif, Q, axis=0)
        for i, ti in enumerate(tt_o):
            w.writerow([ti] + [f"{pq[qi][i]:.6g}" for qi in range(len(Q))] + [f"{np.mean(dif[:, i] > 0):.4g}"])
    def omet(ds):
        return {"arr_m60": np.array([at(d, "ARR", 60) for d in ds]), "arr_m120": np.array([at(d, "ARR", 120) for d in ds]),
                "net_cum_m60": np.array([at(d, "Cumulative Revenue", 60) - at(d, "Cumulative Programme Spend", 60) for d in ds])}
    a, b = omet(o_cf), omet(o_wf)
    order_only = {"split": "30 months each, switch at month 30",
                  "p_churn_first_beats_win_first": {k: float(np.mean(a[k] > b[k])) for k in a},
                  "count_churn_first_beats_win_first": {k: int(np.sum(a[k] > b[k])) for k in a},
                  "cf_minus_wf_arr_m60": pct(a["arr_m60"] - b["arr_m60"]),
                  "drivers_spearman": sp(a["arr_m60"] - b["arr_m60"])}
    od_diff = a["arr_m60"] - b["arr_m60"]
    terc = {}
    for k in sorted(names, key=lambda k: -abs(order_only["drivers_spearman"][k]))[:4]:
        cut = np.percentile(X[k], [100 / 3, 200 / 3])
        bins = np.digitize(X[k], cut)
        terc[k] = {f"T{i + 1} ({X[k][bins == i].min():.4g}-{X[k][bins == i].max():.4g})":
                   [int(np.sum(od_diff[bins == i] > 0)), int(np.sum(bins == i))] for i in range(3)}
    order_only["cf_ahead_by_tercile_counts"] = terc

    # base parameter set (50/50) and no programme: month when sales capacity first binds (structure, one run each)
    bb = validate.run_batch(m["py_path"], [dict(params=validate.base_params(spec), final_time=m["final_time"],
                                                 time_step=m["time_step"], saveper_dt=True, return_columns=COLS),
                                            dict(params=dict(validate.base_params(spec), **{"total programme budget": 0}),
                                                 final_time=m["final_time"], time_step=m["time_step"], saveper_dt=True,
                                                 return_columns=COLS)])
    def first_bind(d):
        hit = np.nonzero(np.asarray(d["deal closings"]) >= np.asarray(d["sales capacity"]) * (1 - 1e-9))[0]
        return float(np.asarray(d.index)[hit[0]]) if hit.size else None
    capacity_onset_base_runs = {"50/50 base parameters": first_bind(bb[0]), "no programme, base parameters": first_bind(bb[1])}

    # bands over time per scenario (ARR, Customers) for gate 9
    t = np.asarray(per["no programme"][0].index, float)
    with open(os.path.join(HERE, "scenario_bands.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        hdr = ["time"]
        cols = []
        for name in [p["name"] for p in pols]:
            for c in ("ARR", "Customers"):
                arr = np.vstack([np.asarray(d[c], float) for d in per[name]])
                cols.append(np.percentile(arr, Q, axis=0))
                hdr += [f"{name}|{c}|P{q}" for q in Q]
        w.writerow(hdr)
        for i, ti in enumerate(t):
            w.writerow([ti] + [f"{c[qi][i]:.6g}" for c in cols for qi in range(len(Q))])

    # loop dominance restricted to loops through Customers (renormalized from loop_dominance.json, base run)
    ld = json.load(open(os.path.join(HERE, "loop_dominance.json")))
    names_by_id = {l["id"]: l.get("name") for l in ld["loops"]}
    sub = [l for l in ld["loops"] if "Customers" in l["variables"]]
    rel = np.array([[np.nan if x is None else x for x in ld["relative_scores"][l["id"]]] for l in sub])
    tt = np.asarray(ld["time"], float)
    with np.errstate(invalid="ignore", divide="ignore"):
        renorm = rel / np.nansum(np.abs(rel), axis=0)
    dom, periods = [], []
    for c in range(renorm.shape[1]):
        col = renorm[:, c]
        dom.append(None if np.all(np.isnan(col)) else int(np.nanargmax(np.abs(col))))
    start = 0
    for c in range(1, len(dom) + 1):
        if c == len(dom) or dom[c] != dom[start]:
            if dom[start] is not None:
                periods.append({"start": float(tt[start]), "end": float(tt[c - 1]), "loop": sub[dom[start]]["name"],
                                "mean_share": float(np.nanmean(np.abs(renorm[dom[start], start:c])))})
            start = c
    merged = []
    for p in periods:   # fold periods shorter than 1 month into the previous one
        if merged and (p["end"] - p["start"] < 1.0 or p["loop"] == merged[-1]["loop"]):
            merged[-1]["end"] = p["end"]
        else:
            merged.append(p)

    R = {"n": n, "seed": seed, "consistency_with_policy_results_max_rel": consistency,
         "scenarios": scen, "p_best_arr_m60": p_best, "pairwise_p_row_beats_col_arr_m60": pairwise,
         "p_churn_first_beats_win_first": cf_wf, "cf_minus_wf_arr_m60": pct(d_cf_wf),
         "drivers_spearman": drivers, "top_drivers_cf_vs_wf": top, "p_cf_ahead_by_tercile": terciles,
         "breakeven": breakeven, "no_programme": {"arr_m60": pct(base["arr_m60"]),
                                                  "capacity_bound_share_m0_60": pct(base["capacity_bound_share_m0_60"]),
                                                  "p_capacity_binds_before_m60": float(np.mean(base["capacity_bound_share_m0_60"] > 0))},
         "count_churn_first_beats_win_first_24_36": cf_wf_count,
         "dominance_model_wide_base_run": [{"start": p["start"], "end": p["end"], "loop": names_by_id.get(p["loop"]),
                                            "mean_relative_score": p["mean_relative_score"]} for p in ld["dominance"]],
         "dominance_customer_loops_base_run": merged, "order_only": order_only,
         "capacity_onset_base_runs": capacity_onset_base_runs}
    # record-only: sha256 of the files this run read and wrote, so a later tool can tell if either changed
    written = list(WRITES)
    read = [os.path.basename(__file__), "validation.toml", spec["model"]["mdl"], spec["model"]["py"]] + list(READS)
    sha = lambda f: hashlib.sha256(open(os.path.join(HERE, f), "rb").read()).hexdigest()  # noqa: E731
    R["output_files"] = {f: sha(f) for f in written}
    R["inputs"] = {f: sha(f) for f in read}
    json.dump(R, open(os.path.join(HERE, "gate8_results.json"), "w"), indent=1)
    print(json.dumps({k: R[k] for k in ("consistency_with_policy_results_max_rel", "p_best_arr_m60", "p_churn_first_beats_win_first",
                                         "cf_minus_wf_arr_m60", "top_drivers_cf_vs_wf", "p_cf_ahead_by_tercile")}, indent=1))
    for key in ("primary_30_30", "variant_24_36"):
        b = R["breakeven"][key]
        print(key, {k: b[k] for k in b if k.startswith("count_") or k == "kstar_crossing_percentiles"})
    print("order only:", json.dumps(order_only["count_churn_first_beats_win_first"]), json.dumps(order_only["cf_ahead_by_tercile_counts"]))
    print("24/36:", json.dumps(cf_wf_count))
    print("model-wide dominance:", [(p["start"], p["end"], p["loop"]) for p in R["dominance_model_wide_base_run"]])
    return 0


if __name__ == "__main__":
    sys.exit(main())
