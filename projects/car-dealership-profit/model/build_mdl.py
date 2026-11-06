"""Writes car_dealership_profit.mdl from ../model_spec.py (stocks and equations), ../validation.toml (parameter bases, ranges,
domains, confidence) and ../settled_initial.json (initial stocks from settle.py), so the .mdl defaults and the spec cannot
drift apart.  Run: .venv/bin/python -I projects/car-dealership-profit/model/build_mdl.py"""
import json
import os
import sys
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import model_spec as M  # noqa: E402

SPEC = tomllib.load(open(os.path.join(HERE, "..", "validation.toml"), "rb"))
P = SPEC["parameters"]
SET = json.load(open(os.path.join(HERE, "..", "settled_initial.json")))["initial"]


def num(x):
    return "%.10g" % x


def bounds(lo, hi):
    return " [%s,%s]" % (num(lo), num(hi))


out = ["{UTF-8}"]


def emit(name, expr, units, note):
    out.append("%s=\n\t%s\n\t~\t%s\n\t~\t%s\n\t|\n" % (name, expr, units, note))


# ---- stocks
for name, unit, ini, infl, outf, kind in M.STOCKS:
    terms = []
    if infl: terms.append("(%s)" % infl if any(c in infl for c in "+-") else infl)
    if outf: terms.append("(%s)" % outf if any(c in outf for c in "+-") else outf)
    body = " - ".join(terms) if len(terms) == 2 else (terms[0] if infl else "-" + terms[0])
    emit(name, "INTEG (%s, %s)" % (body, ini), unit, kind[0].upper() + kind[1:] + ". Model: sd-forge car-dealership-profit; structure in 04_stock_flow.md.")
# ---- auxiliaries and flows
for name, unit, eq in M.AUX:
    emit(name, eq, unit, "")
# ---- parameters (uncertain constants, base from validation.toml)
for name, meta in M.PARAMS_META.items():
    v = P[name]
    lo, hi = v["domain"]
    rng = ("fixed in the Monte Carlo (a store policy or scenario input); lever range %s to %s for exploration." % (num(v["low"]), num(v["high"]))) if v["distribution"] == "fixed" else \
        "Range %s to %s, %s." % (num(v["low"]), num(v["high"]), v["distribution"])
    emit(name, num(v["base"]), v["unit"] + bounds(lo, hi), "%s Confidence: %s. Source: assumptions_register.md." % (rng, v["confidence"]))
# ---- definition constants
NOTE = {"days per month": "Unit conversion (365/12 rounded).", "months per year": "Unit conversion.",
        "vehicles per household purchase": "One vehicle per household purchase; unit conversion.",
        "number of lease stages": "Three-stage chain gives the lease term a spread of lease lengths.",
        "simulation horizon": "Gate 1: 180 months; sizes the source stocks so they never go negative.",
        "minimum owner base": "Guard against dividing by zero; inactive at base.",
        "minimum used sales rate": "Guard against dividing by zero; inactive at base.",
        "minimum sellout time": "Physical limit: sales cannot empty the lot faster than this (about a week); inactive at base."}
for name, (val, unit) in M.CONSTANTS.items():
    emit(name, num(val), unit, NOTE[name])
# ---- initial stocks, reference sales (settled by settle.py; fixed)
UNIT = {"initial prospects": "Household", "initial owners": "Household", "initial lessees per stage": "Household",
        "initial new inventory": "Vehicle", "initial new vehicles on order": "Vehicle", "initial used frontline inventory": "Vehicle",
        "initial reconditioning pipeline": "Vehicle", "initial service customers": "Household", "initial technicians": "Technician",
        "initial inventory at cost": "USD", "initial floorplan debt": "USD", "initial cash": "USD",
        "reference new sales": "Household/Month", "reference used sales": "Household/Month", "initial used supply outside": "Vehicle"}
for name, unit in UNIT.items():
    emit(name, num(SET[name]), unit + " [0,?]", "Fixed. Base-parameter steady state from settle.py (assumptions_register.md); not sampled.")

m = SPEC["model"]
out.append("""********************************************************
\t.Control
********************************************************~
\t\tSimulation Control Parameters
\t|

FINAL TIME  = %g
\t~\tMonth
\t~\t15 years: >= 3x the longest delay (replacement cycle, up to 60-72 months); decision horizon 60 months, valuation 120.
\t|

INITIAL TIME  = 0
\t~\tMonth
\t~\t\t|

SAVEPER  = %g
\t~\tMonth [0,?]
\t~\t\t|

TIME STEP  = %g
\t~\tMonth [0,?]
\t~\tAt most 1/4 of the shortest time constant in the ranges (reconditioning time, 0.25 month); divides 60, 120 and 180.
\t|
""" % (m["final_time"], m["saveper"], m["time_step"]))
path = os.path.join(HERE, "car_dealership_profit.mdl")
open(path, "w").write("\n".join(out))
names = [s[0] for s in M.STOCKS] + [a[0] for a in M.AUX] + list(M.PARAMS_META) + list(M.CONSTANTS) + list(UNIT)
assert len(names) == len(set(names)), [n for n in names if names.count(n) > 1]
print(path, len(names), "variables")
