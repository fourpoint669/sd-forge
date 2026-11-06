"""Writes saas_churn_vs_winrate.mdl. Constant values come from ../validation.toml (base), so the .mdl defaults and the
spec cannot drift apart. Run: .venv/bin/python -I projects/saas-churn-vs-winrate/model/build_mdl.py"""
import os
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = tomllib.load(open(os.path.join(HERE, "..", "validation.toml"), "rb"))
P = SPEC["parameters"]


def const(name, note):
    v = P[name]
    lo, hi = v["domain"]
    rng = f" [{lo:g},{'?' if hi == float('inf') else f'{hi:g}'}]"
    return name, f"{v['base']:g}", v["unit"] + rng, f"{note} Range {v['low']:g}-{v['high']:g}, {v.get('distribution')}. " \
                                                    f"Confidence: {v['confidence']}. Source: assumptions_register.md."


def fixed(name, value, unit, note):
    return name, value, unit, note


EQ = [
    # ---- stocks ----
    ("Potential Customers", "INTEG (re entry + market entries - evaluation starts, initial total market - initial customers)", "Firm",
     "Target firms that are neither customers, in an evaluation, nor cooling off. Original model for sd-forge; customer engine as in projects/bass-b2b-adoption."),
    ("Firms in Evaluation", "INTEG (evaluation starts - deals won - deals lost, initial firms in evaluation)", "Firm",
     "Open sales opportunities; first-order sales-cycle delay."),
    ("Customers", "INTEG (deals won - churn, initial customers)", "Firm", "Paying customer firms (logos)."),
    ("Cooling Off Firms", "INTEG (deals lost + churn - re entry, initial cooling off firms)", "Firm",
     "Firms that lost a deal or churned; return to the pool after the cool-off time."),
    ("Firms Yet To Enter", "INTEG (-market entries, initial firms yet to enter)", "Firm",
     "Source stock for linear market growth; empties exactly at the market growth horizon (keeps the firm total conserved)."),
    ("Recently Churned Firms", "INTEG (churn - detractor fade, 0)", "Firm",
     "Information co-flow: count of recent churners (detractors). Not part of the firm conservation group."),
    ("CS Capacity", "INTEG (CS capacity change, 0)", "Firm",
     "Customers the churn programme can cover, additional to today's CS; goal-seeks to funded capacity with a ramp-up delay."),
    ("Win Rate Capability", "INTEG (capability change, 0)", "Dmnl",
     "Enablement level 0-1, additional to today's; goal-seeks to the target funded by spend with a ramp-up delay."),
    ("ARR", "INTEG (new ARR + expansion ARR - churned ARR, initial customers * new customer ACV)", "USD/Year",
     "Annual recurring revenue (objective at month 60)."),
    ("Cumulative Revenue", "INTEG (revenue recognition, 0)", "USD", "Revenue recognised since month 0."),
    ("Cumulative Programme Spend", "INTEG (total programme spend, 0)", "USD", "Programme dollars spent since month 0."),
    # ---- demand generation ----
    ("evaluation starts", "marketing driven starts + word of mouth starts", "Firm/Month", "Bass adoption flow into evaluation."),
    ("marketing driven starts", "marketing reach rate monthly * Potential Customers", "Firm/Month", "Bass innovation term."),
    ("word of mouth starts",
     "word of mouth rate monthly * Potential Customers * MAX(0, customer share - negative word of mouth multiplier * detractor share)",
     "Firm/Month", "Bass imitation term, reduced by recent churners when the multiplier (parameter C) > 0; never negative."),
    ("customer share", "Customers / total market", "Dmnl", "Share of the target market that are customers."),
    ("detractor share", "Recently Churned Firms / total market", "Dmnl", "Share of the market that churned recently."),
    ("marketing reach rate monthly", "marketing reach rate / months per year", "1/Month", ""),
    ("word of mouth rate monthly", "word of mouth rate / months per year", "1/Month", ""),
    # ---- market pool ----
    ("re entry", "Cooling Off Firms / cool off time", "Firm/Month", "First-order return to the potential pool."),
    ("market entries", "market growth rate monthly * initial total market * market growth active", "Firm/Month",
     "Linear market growth; stops at the market growth horizon."),
    ("market growth active", "IF THEN ELSE(Time < market growth horizon, 1, 0)", "Dmnl", ""),
    ("market growth rate monthly", "market growth rate / months per year", "1/Month", ""),
    ("initial firms yet to enter", "market growth rate * initial total market * market growth horizon / months per year", "Firm",
     "All firms that enter within the horizon."),
    ("total market", "initial total market + initial firms yet to enter - Firms Yet To Enter", "Firm", "Current market size."),
    # ---- sales pipeline ----
    ("deal closings", "MIN(Firms in Evaluation / sales cycle time, sales capacity)", "Firm/Month",
     "Opportunities closed (won or lost); limited by sales capacity, excess stays in the pipeline."),
    ("sales capacity", "initial sales capacity * (1 + sales capacity growth rate * Time / months per year)", "Firm/Month",
     "Closings the sales team can handle; grows linearly with time when parameter B > 0 (not driven by revenue)."),
    ("deals won", "deal closings * effective win rate", "Firm/Month", ""),
    ("deals lost", "deal closings * (1 - effective win rate)", "Firm/Month", ""),
    ("effective win rate", "base win rate + maximum win rate uplift * Win Rate Capability", "Dmnl",
     "At most 1: base win rate domain <= 0.9, uplift domain <= 0.1."),
    # ---- customer base ----
    ("churn", "Customers * effective churn fraction", "Firm/Month", "Logo churn."),
    ("effective churn fraction", "base churn rate monthly * (1 - churn reduction)", "1/Month", ""),
    ("base churn rate monthly", "base annual churn rate / months per year", "1/Month", ""),
    ("detractor fade", "Recently Churned Firms / detractor memory time", "Firm/Month", ""),
    # ---- churn programme ----
    ("churn programme spend", "monthly programme budget * programme active * churn share now", "USD/Month", ""),
    ("funded CS capacity", "churn programme spend / CS cost per covered firm", "Firm", "Customers the current spend pays to cover."),
    ("CS capacity change", "(funded CS capacity - CS Capacity) / CS ramp up time", "Firm/Month", "Goal seeking (loop B7)."),
    ("CS coverage", "CS Capacity / MAX(Customers, minimum customer base)", "Dmnl", "Diluted as Customers grow (loop B11)."),
    ("CS effect", "1 - EXP(-CS coverage / coverage scale)", "Dmnl", "Diminishing returns in coverage."),
    ("churn reduction", "maximum churn reduction * CS effect", "Dmnl", ""),
    # ---- win-rate programme ----
    ("win rate programme spend", "monthly programme budget * programme active * (1 - churn share now)", "USD/Month", ""),
    ("target capability", "1 - EXP(-win rate programme spend / win spend scale)", "Dmnl", "Diminishing returns in spend."),
    ("capability change", "(target capability - Win Rate Capability) / enablement ramp up time", "1/Month", "Goal seeking (loop B8)."),
    # ---- revenue ----
    ("new ARR", "deals won * new customer ACV", "USD/(Year*Month)", ""),
    ("expansion ARR", "ARR * effective expansion rate monthly * expansion headroom", "USD/(Year*Month)",
     "Net expansion, slowing as average ARR per customer nears the ceiling (loop B14)."),
    ("churned ARR", "ARR * effective churn fraction", "USD/(Year*Month)", "Churners carry average ARR (assumption S9)."),
    ("ARR per customer", "ARR / MAX(Customers, minimum customer base)", "USD/(Firm*Year)", ""),
    ("expansion headroom", "1 - ARR per customer / (new customer ACV * expansion ceiling multiple)", "Dmnl", ""),
    ("expansion lift", "expansion lift at full CS effect * CS effect", "1/Year", "Parameter A; 0 at base."),
    ("effective expansion rate", "base net expansion rate + expansion lift", "1/Year", ""),
    ("effective expansion rate monthly", "effective expansion rate / months per year", "1/Month", ""),
    ("revenue recognition", "ARR / months per year", "USD/Month", "ARR (USD/Year) per Month: the /12 conversion (gate 1)."),
    ("cumulative revenue net of programme spend", "Cumulative Revenue - Cumulative Programme Spend", "USD", ""),
    # ---- budget ----
    ("monthly programme budget", "total programme budget / programme months", "USD/Month", ""),
    ("programme active", "IF THEN ELSE(Time < programme months, 1, 0)", "Dmnl", ""),
    ("churn share now", "IF THEN ELSE(Time < phase switch month, churn share phase 1, churn share phase 2)", "Dmnl", ""),
    ("total programme spend", "churn programme spend + win rate programme spend", "USD/Month", ""),
]

CONST = [
    const("marketing reach rate", "Bass p for entry into evaluation."),
    const("word of mouth rate", "Bass q for entry into evaluation."),
    const("negative word of mouth multiplier", "Parameter C (optional, default 0)."),
    const("cool off time", "Time before a lost or churned firm re-evaluates."),
    const("market growth rate", "Linear market growth (optional, default 0)."),
    const("initial total market", "Illustrative; replace with your own market sizing."),
    const("sales cycle time", "Average time in evaluation."),
    const("initial sales capacity", "Closings per month (won + lost)."),
    const("sales capacity growth rate", "Parameter B (optional, default 0)."),
    const("base win rate", "Win rate without the programme."),
    const("base annual churn rate", "Logo churn without the programme."),
    const("detractor memory time", "How long a churner affects referrals."),
    const("initial customers", "Design partners at launch."),
    const("CS cost per covered firm", "Fully loaded CSM cost per account per month."),
    const("CS ramp up time", "Hiring and onboarding delay."),
    const("coverage scale", "Coverage giving 63% of the maximum churn effect."),
    const("maximum churn reduction", "Churn cut at full CS effect."),
    const("win spend scale", "Spend giving 63% of full enablement capability."),
    const("enablement ramp up time", "Adoption delay of enablement."),
    const("maximum win rate uplift", "Win-rate points at full capability."),
    const("new customer ACV", "Annual contract value of a new customer."),
    const("base net expansion rate", "Expansion net of contraction on retained ARR."),
    const("expansion lift at full CS effect", "Parameter A (optional, default 0)."),
    const("expansion ceiling multiple", "Ceiling on average ARR per customer as a multiple of ACV."),
    const("total programme budget", "Same total in every scenario; illustrative."),
    const("phase switch month", "End of phase 1 (scenario lever, fixed)."),
    const("churn share phase 1", "Share of spend on churn before the switch (scenario lever)."),
    const("churn share phase 2", "Share of spend on churn after the switch (scenario lever)."),
    fixed("market growth horizon", "120", "Month", "Market entries stop here (end of the 120-month run)."),
    fixed("programme months", "60", "Month", "Budget is spent evenly over the 5-year decision horizon."),
    fixed("minimum customer base", "1", "Firm", "Keeps ratios per customer finite when Customers = 0."),
    fixed("initial firms in evaluation", "0", "Firm [0,?]", "Launch starts with an empty pipeline."),
    fixed("initial cooling off firms", "0", "Firm [0,?]", ""),
    fixed("months per year", "12", "Month/Year", "Unit conversion."),
]

out = ["{UTF-8}"]
for name, expr, units, note in EQ + CONST:
    out.append(f"{name}=\n\t{expr}\n\t~\t{units}\n\t~\t{note}\n\t|\n")
m = SPEC["model"]
out.append("""********************************************************
\t.Control
********************************************************~
\t\tSimulation Control Parameters
\t|

FINAL TIME  = %g
\t~\tMonth
\t~\tTen years: >= 3x the longest delay (36-month cool-off); decision horizon 60 months.
\t|

INITIAL TIME  = 0
\t~\tMonth
\t~\t\t|

SAVEPER  = %g
\t~\tMonth [0,?]
\t~\t\t|

TIME STEP  = %g
\t~\tMonth [0,?]
\t~\tAt most 1/8 of the shortest time constant in the ranges (CS ramp-up 2 months); divides 24, 60 and 120.
\t|
""" % (m["final_time"], m["saveper"], m["time_step"]))
path = os.path.join(HERE, "saas_churn_vs_winrate.mdl")
open(path, "w").write("\n".join(out))
names = [e[0] for e in EQ + CONST]
assert len(names) == len(set(names))
print(path, len(names), "variables")
