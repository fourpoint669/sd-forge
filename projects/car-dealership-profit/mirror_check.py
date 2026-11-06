"""Compares the PySD translation with the independent Euler mirror (settle.py) on the base run.
Run from the repo root: .venv/bin/python -I projects/car-dealership-profit/mirror_check.py"""
import sys, json, warnings, numpy as np
warnings.simplefilter("ignore")
sys.path.insert(0, "projects/car-dealership-profit")
import pysd, settle, model_spec as M
m = pysd.load("projects/car-dealership-profit/model/car_dealership_profit.py")
df = m.run(return_columns=None, params={})
print("PySD rows", len(df), "cols", df.shape[1])
init = json.load(open("projects/car-dealership-profit/settled_initial.json"))["initial"]
V = settle.base_values(); V["reference new sales"] = init["reference new sales"]; V["reference used sales"] = init["reference used sales"]; V["initial cash"] = init["initial cash"]
S = settle.initial_stocks(V, init)
keys = ["net profit", "Cumulative Net Profit", "New Inventory", "Used Frontline Inventory", "Owners", "Service Customers", "Cash", "Floorplan Debt", "used price discount", "absorption rate", "Households Elsewhere", "Cumulative Discounted Cash Flow"]
St, tr, Vend = settle.run(V, S, 180, 0.0625, record=keys)
t_idx = np.arange(0, 180 + 1e-9, 0.0625)
cols = {c.lower(): c for c in df.columns}
def col(n):
    for c in df.columns:
        if c.lower().replace("_", " ") == n.lower(): return c
    raise KeyError(n)
sub = df.index.values
print("%-34s %14s %14s %10s" % ("variable", "PySD final", "mirror final", "max rel dif"))
for k in keys:
    a = np.asarray(df[col(k)], float); b = np.interp(sub, t_idx, np.asarray(tr[k], float))
    sc = max(1e-9, np.abs(b).max())
    print("%-34s %14.6g %14.6g %10.2e" % (k, a[-1], b[-1], np.abs(a - b).max() / sc))
a = np.asarray(df[col("net profit")], float); print("net profit flat: min %.6g max %.6g" % (a.min(), a.max()))
