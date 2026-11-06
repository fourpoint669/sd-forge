"""A1: T5 reference case of bass-b2b-adoption across sales cycle times tau (scratch copy; spec read, never edited)."""
import sys, numpy as np
sys.path.insert(0, sys.argv[1])
import validate
spec = validate.load_spec(sys.argv[2]); ref = spec["reference"]; base = validate.base_params(spec)
py = spec["model"]["py_path"]
rows = []
for tau, dt in [(0.5, 0.25), (0.5, 0.01), (0.25, 0.01), (0.1, 0.01), (0.05, 0.01), (0.02, 0.01), (0.01, 0.005)]:
    rp = dict(base, **ref["set"]); rp["sales cycle time"] = tau
    df = validate.run_batch(py, [dict(params=rp, final_time=spec["model"]["final_time"], time_step=dt, saveper_dt=True)], workers=1)[0]
    args = {a: rp[v["param"]] * v.get("factor", 1.0) for a, v in ref["args"].items()}
    sim = sum(np.asarray(df[c], float) for c in ref["compare"])
    err = validate.nrmse(sim, validate.bass_cumulative(df.index, **args))
    t_sim = float(df.index[int(np.argmax(np.asarray(df[ref["peak"]["var"]], float)))])
    t_star = validate.bass_peak_time(args["p"], args["q"])
    pred = t_star * (1 + args["q"] * tau)
    rows.append((tau, dt, t_sim, t_star, t_sim - t_star, pred, err, abs(t_sim - t_star) <= ref["peak"]["tolerance"] and err <= ref["nrmse_max"]))
print(f"p={args['p']:.6g}/month q={args['q']:.6g}/month t*={t_star:.4f}; tolerance {ref['peak']['tolerance']} months, nrmse_max {ref['nrmse_max']}")
print("| tau (months) | dt | t_peak sim | t* | t_peak - t* | t*(1+q*tau) | NRMSE | T5 pass |")
print("|---|---|---|---|---|---|---|---|")
for r in rows:
    print(f"| {r[0]} | {r[1]} | {r[2]:.3f} | {r[3]:.3f} | {r[4]:+.3f} | {r[5]:.3f} | {r[6]:.5f} | {r[7]} |")
