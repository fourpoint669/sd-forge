"""Independent numeric mirror of the gate 4 equations (model_spec.py) and the steady-state solver.

Usage:  .venv/bin/python -I projects/car-dealership-profit/settle.py [--write]

The mirror evaluates each equation string from model_spec.AUX / STOCKS with Euler steps. It serves two purposes:
  1. settle: run the base parameters until every stock stops moving, and print the settled stocks. Those numbers
     become the fixed `initial ...` constants (gate 6). Nothing here is assumed: they come from this run.
  2. oracle: gate 7 compares the PySD model against this mirror (a second implementation of the same equations).
"""
import math, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import model_spec as M

NAMES = sorted(list({a[0] for a in M.AUX} | {s[0] for s in M.STOCKS} | set(M.CONSTANTS) | set(M.PARAMS_META)
                    | set(M.INITIAL_NAMES.values()) | {"initial used supply outside", "reference new sales", "reference used sales", "initial cash"}), key=lambda s: -len(s))
PAT = re.compile("|".join(re.escape(n) for n in NAMES) + r"|Time|IF THEN ELSE|MIN|MAX|EXP")


def compile_expr(expr):
    def sub(m):
        t = m.group(0)
        if t == "IF THEN ELSE": return "ITE"
        if t in ("MIN", "MAX", "EXP"): return t.lower() + "_"
        if t == "Time": return "V['Time']"
        return "V[%r]" % t
    return compile(PAT.sub(sub, expr), "<eq>", "eval")


def ITE(c, a, b): return a if c else b


ENV = {"ITE": ITE, "min_": min, "max_": max, "exp_": math.exp}
AUXC = [(n, compile_expr(eq)) for n, u, eq in M.AUX]
STC = []
for n, u, ini, infl, outf, kind in M.STOCKS:
    STC.append((n, ini, compile_expr(infl) if infl else None, compile_expr(outf) if outf else None))


def order_aux():
    """Topological order of auxiliaries (dependencies among auxiliaries only; stocks and constants are inputs)."""
    auxn = {n for n, _ in AUXC}
    dep = {n: {x for x in PAT.findall(eq) if x in auxn and x != n} for n, u, eq in M.AUX}
    done, out = set(), []
    while len(out) < len(dep):
        prog = False
        for n in dep:
            if n not in done and dep[n] <= done:
                done.add(n); out.append(n); prog = True
        if not prog: raise RuntimeError("algebraic loop among auxiliaries: " + str(sorted(set(dep) - done)))
    return out


ORDER = order_aux()
AUXD = dict(AUXC)


def base_values(overrides=None):
    V = {k: v[0] for k, v in M.CONSTANTS.items()}
    V.update({k: v["base"] for k, v in M.PARAMS_META.items()})
    if overrides: V.update(overrides)
    return V


def run(V, stocks, final_time, dt, record=None):
    """Euler integration; stocks is {name: initial}. Returns (stocks, trace) with trace[name] lists if record."""
    V = dict(V); S = dict(stocks)
    trace = {k: [] for k in (record or [])}
    steps = int(round(final_time / dt))
    for i in range(steps + 1):
        V["Time"] = i * dt
        V.update(S)
        for n in ORDER: V[n] = eval(AUXD[n], ENV, {"V": V})
        for k in trace: trace[k].append(V[k])
        if i == steps: break
        d = {}
        for n, ini, inc, outc in STC:
            fl = eval(inc, ENV, {"V": V}) if inc else 0.0
            fo = eval(outc, ENV, {"V": V}) if outc else 0.0
            d[n] = fl - fo
        for n in S: S[n] += dt * d[n]
    return S, trace, V


def initial_stocks(V, init):
    """Stock initial values from the formula strings of model_spec.STOCKS (init = settled values by name)."""
    S = {}
    for n, u, ini, infl, outf, kind in M.STOCKS:
        if ini in M.INITIAL_NAMES.values():
            S[n] = init[ini]
        elif ini == "0":
            S[n] = 0.0
        elif ini in ("reference new sales", "reference used sales"):
            S[n] = init[ini]
        elif ini == "initial used supply outside":
            S[n] = init["initial used supply outside"]
        else:
            S[n] = eval(compile_expr(ini), ENV, {"V": V})
    return S


def guess():
    return {"initial prospects": 300.0, "initial owners": 7000.0, "initial lessees per stage": 250.0,
            "initial new inventory": 160.0, "initial new vehicles on order": 80.0, "initial used frontline inventory": 90.0,
            "initial reconditioning pipeline": 20.0, "initial service customers": 13000.0, "initial technicians": 23.0,
            "initial inventory at cost": 9.0e6, "initial floorplan debt": 8.1e6, "initial cash": 1.5e6,
            "reference new sales": 83.0, "reference used sales": 67.0, "initial used supply outside": 1.0e6}


def settle(overrides=None, months=4000, dt=0.125):
    V = base_values(overrides)
    init = guess()
    for rnd in range(3):
        V["reference new sales"] = init["reference new sales"]; V["reference used sales"] = init["reference used sales"]; V["initial cash"] = init["initial cash"]
        S = initial_stocks(V, init)
        S, tr, Vend = run(V, S, months, dt)
        # re-anchor the derived initial values: reference sales and inventory at cost / debt follow the settled stocks
        init.update({"initial prospects": S["Prospects"], "initial owners": S["Owners"],
                     "initial lessees per stage": S["Lessees Early"], "initial new inventory": S["New Inventory"],
                     "initial new vehicles on order": S["New Vehicles On Order"], "initial used frontline inventory": S["Used Frontline Inventory"],
                     "initial reconditioning pipeline": S["Reconditioning Pipeline"], "initial service customers": S["Service Customers"],
                     "initial technicians": S["Technicians"], "reference new sales": Vend["new sales"], "reference used sales": Vend["used sales"]})
        inv = S["New Inventory"] * V["new vehicle unit cost"] + (S["Used Frontline Inventory"] + S["Reconditioning Pipeline"]) * V["used vehicle unit cost"]
        init["initial inventory at cost"] = inv
        init["initial floorplan debt"] = V["advance rate"] * inv
    # check it is flat: run 120 more months from the settled values and report the largest relative move
    V["reference new sales"] = init["reference new sales"]; V["reference used sales"] = init["reference used sales"]; V["initial cash"] = init["initial cash"]
    S0 = initial_stocks(V, init)
    S1, tr, V1 = run(V, S0, 120, dt)
    moves = {k: abs(S1[k] - S0[k]) / max(1.0, abs(S0[k])) for k in S0 if k in M.INITIAL_NAMES and k != "Cash"}
    return init, V1, moves, tr


if __name__ == "__main__":
    ov = {}
    for a in sys.argv[1:]:
        if "=" in a and not a.startswith("--"):
            k, v = a.split("="); ov[k.replace("_", " ")] = float(v)
    init, V, moves, tr = settle(ov)
    if "--write" in sys.argv:
        import json
        out = {"initial": init, "base_flows": {k: V[k] for k in V if isinstance(V[k], float)}, "max_relative_move_120_months": max(moves.values())}
        json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "settled_initial.json"), "w"), indent=1, sort_keys=True)
    print("settled initial values:")
    for k, v in init.items(): print("  %-34s %.6g" % (k, v))
    print("max relative move of any settled stock in 120 months:", "%.3g" % max(moves.values()), max(moves, key=moves.get))
    keys = ["new sales", "used sales", "lease starts", "repeat to store", "ro done", "utilisation", "store loyalty", "used days supply",
            "used price discount", "new gross", "used gross", "F and I income", "service gross", "parts gross", "lease remarketing gain",
            "total gross", "commissions", "technician payroll", "wholesale loss", "floorplan interest", "net profit", "absorption rate",
            "auction buys", "trade ins", "off lease returns", "wholesale exits", "capacity", "ro demand"]
    print("base flows at the end of the settle check:")
    for k in keys: print("  %-26s %12.4f" % (k, V[k]))
    rev = V["new sales"] * V["new vehicle unit cost"] * 1.0 + 0  # cost only; margin reported against gross below
    print("  net profit / total gross       %.3f" % (V["net profit"] / V["total gross"]))
    rev = V["new sales"] * (V["new vehicle unit cost"] + V["new gross per vehicle"]) + V["used sales"] * V["used retail price"] + V["ro done"] * 480.0
    print("  net profit / revenue proxy (vehicles at unit cost + gross, used at retail price, service at an assumed $480 per RO; a proxy, not a model output): %.4f" % (V["net profit"] / rev))
    fixed_gross = V["service gross"] + V["parts gross"]
    print("  fixed-ops gross share of total gross (before tech pay): %.3f" % (fixed_gross / V["total gross"]))
    print("  fixed-ops gross share after tech pay: %.3f" % ((fixed_gross - V["technician payroll"]) / (V["total gross"] - V["technician payroll"])))
