"""Delay audit of a validated project (report only; never changes the model).

Usage:  python -I engine/delay_audit.py [--projects-root DIR] projects/<model>|<model>      -> writes delay_audit.json and delay_audit.md

Reads the committed PySD .py. Every stock is classified by the form of its outflows (auxiliaries are inlined):
  drain          outflow = S / tau (x other factors)            first-order delay, residence time tau
  drain_capped   outflow = min(S / tau, capacity) (x factors)   first-order delay that becomes a fixed-rate queue
                                                                 when the capacity binds
  goal_seeking   net flow = (X - S) / tau                       first-order adjustment (the SMOOTH structure)
  rate           outflow = S x k                                first-order exit, average residence 1/k
  coflow         outflow = S x k with k shared by the outflow of a conserved stock (an attribute such as revenue)
  source         outflows do not depend on S                    not a delay
  accumulator    no outflow                                     not a delay
delay_type: material when the stock is in a [[conservation]] group of validation.toml; information for a drain or
goal-seeking stock outside any conserved group; none for coflow, source and accumulator.
order = number of stocks in the delay chain (1 for every structure above; a DELAY3-like chain would be 3).
tau: the time-constant expression; tau_base / tau_run = its value at t = 0 and its [min, max] over the PySD base run
(for rate forms tau = 1/k). tau_range = the validated [low, high] when tau is a single parameter.
first_order_candidate: every first-order material or information delay. Whether the real-world process is a roughly
fixed delay is a judgment, written by hand below the marker line in delay_audit.md (kept on regeneration).
DELAY/SMOOTH/TREND functions would be listed under 'functions'; engine/export_js.py rejects them.
"""
import ast
import copy
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import explorer_meta  # noqa: E402
import sd_paths  # noqa: E402
import loop_detector as ld  # noqa: E402  (read-only dependency)
import validate  # noqa: E402  (read-only dependency)

MARKER = "<!-- Everything below this line is hand-written judgment and is kept when the audit is regenerated. -->"
DELAY_FUNCS = ("Delay", "DelayN", "DelayFixed", "Smooth", "SmoothN", "Trend", "Forecast", "Initial", "SampleIfTrue")


def _call_name(n):
    return n.func.id if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and not n.args else None


def _literal_sign(node):
    """-1 when this factor is a negative number as written (-1, -2.5), +1 otherwise. Only literals count: a negated
    expression such as -rate() is already handled by signed_terms' unary branch, and counting it here too would
    cancel that out."""
    if (isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant)
            and isinstance(node.operand.value, (int, float)) and not isinstance(node.operand.value, bool)):
        return -1 if node.operand.value > 0 else 1
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return -1 if node.value < 0 else 1
    return 1


def signed_terms(node, sign=1, never=frozenset()):
    """Net-flow expression -> [(sign, flow py name)], for the shapes PySD writes around a rate.

    Sums and differences of rate calls, and a rate wrapped in the forms a translated model puts around one: float(x),
    np.maximum/np.minimum against a bound, and a product or quotient whose only non-exogenous factor is the rate
    (`new_sales() * vehicles_per_household_purchase()`), whose sign follows any negative number written in it.
    `never` is the set of py names that can never be a rate (never_a_flow); without it a constant factor,
    a control or a stock would itself be drawn as a valve. A term this cannot resolve to exactly one rate is
    dropped, as before: the stock then shows no pipe for it rather than a wrong one."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub)):
        return (signed_terms(node.left, sign, never)
                + signed_terms(node.right, sign * (1 if isinstance(node.op, ast.Add) else -1), never))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        return signed_terms(node.operand, -sign if isinstance(node.op, ast.USub) else sign, never)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "float" and len(node.args) == 1:
        return signed_terms(node.args[0], sign, never)
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("maximum", "minimum")
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "np"):
        terms = [t for a in node.args for t in signed_terms(a, sign, never)]
        return terms if len(terms) == 1 else []
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mult, ast.Div)):
        if isinstance(node.op, ast.Div) and signed_terms(node.right, sign, never):
            return []                                             # a rate in the denominator is not that rate
        terms = signed_terms(node.left, sign, never) + signed_terms(node.right, sign, never)
        if len(terms) != 1:
            return []
        flip = _literal_sign(node.left) * _literal_sign(node.right)   # outflow() * -1 drains, it does not fill
        return [(terms[0][0] * flip, terms[0][1])]
    name = _call_name(node)
    return [(sign, name)] if name and name not in never else []


def never_a_flow(comps):
    """The py names that can never be a stock's rate, so never a valve in the diagram: constants and parameters
    (a constant factor is not the flow), the time controls (INTEG(Time, 0) has no valve), and the stocks themselves
    (INTEG(-MIN(Stock/tau, cap)) reduces to the stock, which is a level, not a rate)."""
    return frozenset(p for p, c in comps.items() if c.ctype in ("Constant", "Control", "Stateful"))


class _Inline(ast.NodeTransformer):
    """Replace auxiliary calls by their equations, up to max_depth levels deep."""
    def __init__(self, comps, keep, max_depth=20, depth=0):
        self.comps, self.keep, self.max_depth, self.depth = comps, keep, max_depth, depth

    def visit_Call(self, node):
        name = _call_name(node)
        if name and name in self.comps and name not in self.keep and self.depth < self.max_depth:
            expr = copy.deepcopy(self.comps[name].expr)
            return _Inline(self.comps, self.keep, self.max_depth, self.depth + 1).visit(expr)
        self.generic_visit(node)
        return node


def _calls(node):
    return {n for n in (_call_name(x) for x in ast.walk(node)) if n}


def _strip_float(node):
    while isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "float" and len(node.args) == 1:
        node = node.args[0]
    return node


def _factors(node):
    node = _strip_float(node)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
        return _factors(node.left) + _factors(node.right)
    return [node]


def _additive(node):
    node = _strip_float(node)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _additive(node.left) + _additive(node.right)
    return [node]


def _cap_name(start, stock, comps, stocks):
    """Name of the capacity argument of the np.minimum(stock / tau, capacity) reached from component `start`."""
    seen, todo = set(), [start]
    while todo:
        n = todo.pop()
        if n in seen or n not in comps or comps[n].expr is None:
            continue
        seen.add(n)
        for node in ast.walk(comps[n].expr):
            if _np_min(node) and isinstance(node.func, ast.Attribute):
                names = [_call_name(_strip_float(a)) for a in node.args]
                for i, a in enumerate(node.args):
                    if stock in _calls(a) and names[1 - i]:
                        return names[1 - i]
        todo += [c for c in _calls(comps[n].expr) if c not in stocks]
    return None


def _np_min(node):
    node = _strip_float(node)
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "minimum")


def _classify_outflow(stock, inl, stocks):
    """(form, tau AST or None, cap AST or None, k AST or None) for one inlined outflow expression."""
    for f in _factors(inl):
        f = _strip_float(f)
        if _np_min(f):
            for i, a in enumerate(f.args):
                a = _strip_float(a)
                if (isinstance(a, ast.BinOp) and isinstance(a.op, ast.Div) and _call_name(a.left) == stock
                        and not (_calls(a.right) & stocks)):
                    return "drain_capped", a.right, f.args[1 - i], None
        if (isinstance(f, ast.BinOp) and isinstance(f.op, ast.Div) and _call_name(f.left) == stock
                and not (_calls(f.right) & stocks)):
            return "drain", f.right, None, None
    terms = _additive(inl)
    rests = []
    for t in terms:
        facs = _factors(t)
        hits = [i for i, f in enumerate(facs) if _call_name(f) == stock]
        if len(hits) != 1:
            break
        rest = [f for i, f in enumerate(facs) if i != hits[0]] or [ast.Constant(1.0)]
        k = rest[0]
        for f in rest[1:]:
            k = ast.BinOp(left=k, op=ast.Mult(), right=f)
        rests.append(k)
    else:
        k = rests[0]
        for r in rests[1:]:
            k = ast.BinOp(left=k, op=ast.Add(), right=r)
        return "rate", None, None, k
    if stock not in _calls(inl):
        return "source", None, None, None
    return "other", None, None, None


def _evaluate(expr, model, names, v):
    fn = ld.compile_expr(ast.fix_missing_locations(copy.deepcopy(expr)), names)
    out = np.asarray(fn(v), dtype=float)
    return np.broadcast_to(out, v["time"].shape)


def audit(project_dir):
    spec = validate.load_spec(os.path.join(project_dir, "validation.toml"))
    py = spec["model"]["py_path"]
    model = ld.parse_model(py)
    comps = {k: c for k, c in model.comps.items() if c.ctype != "Control"}
    names = set(comps)
    stocks = {k for k, c in comps.items() if c.ctype == "Stateful"}
    consts = {k for k, c in comps.items() if c.ctype == "Constant"}
    real = {k: c.name for k, c in comps.items()}
    by_real = {v: k for k, v in real.items()}
    conserved = {s for g in spec.get("conservation", []) for s in g["stocks"]}
    tree = ast.parse(open(py).read())
    functions = sorted({n.value.func.id for n in tree.body if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call)
                        and isinstance(n.value.func, ast.Name) and n.value.func.id in DELAY_FUNCS})
    df = validate.run_batch(py, [{"params": validate.base_params(spec)}])[0]
    v = ld.values_from_frame(model, df)
    keep = stocks | consts
    inline = lambda e, d=20: _Inline(comps, keep, d).visit(copy.deepcopy(e))  # noqa: E731

    def shallowest(f):
        """Classification of outflow f at the shallowest inlining depth that recognises a delay form."""
        for d in range(21):
            got = _classify_outflow(s, inline(comps[f].expr, d), stocks)
            if got[0] not in ("other", "source"):
                return got
        return got
    text = lambda e: explorer_meta.equation_text(e, real)  # noqa: E731
    rate_factors = {}
    never = never_a_flow(comps)
    for s in sorted(stocks):
        for sign, f in signed_terms(comps[s].flow, 1, never):
            if sign < 0 and f in comps and comps[f].expr is not None:
                facs = [_call_name(_strip_float(x)) for x in _factors(comps[f].expr)]
                if s in facs:
                    rate_factors.setdefault(s, set()).update(x for x in facs if x and x != s)
    rows = []
    for s in sorted(stocks, key=lambda k: real[k]):
        c = comps[s]
        terms = signed_terms(c.flow, 1, never)
        outs = [f for sign, f in terms if sign < 0]
        ins = [f for sign, f in terms if sign > 0]
        row = {"stock": real[s], "inflows": [real[f] for f in ins], "outflows": [real[f] for f in outs],
               "form": None, "delay_type": "none", "order": None, "tau": None, "tau_var": None, "tau_base": None,
               "tau_run": None, "tau_range": None, "cap": None, "cap_var": None, "state_dependent": None,
               "coflow_of": None, "downstream": [], "first_order_candidate": False}
        tau = None
        f_div = None
        for d in range(21):
            f_div = _strip_float(inline(c.flow, d))
            if isinstance(f_div, ast.BinOp) and isinstance(f_div.op, ast.Div):
                break
        if (isinstance(f_div, ast.BinOp) and isinstance(f_div.op, ast.Div) and isinstance(f_div.left, ast.BinOp)
                and isinstance(f_div.left.op, ast.Sub) and _call_name(f_div.left.right) == s
                and s not in _calls(f_div.left.left) and not (_calls(f_div.right) & stocks)):
            row["form"], tau = "goal_seeking", f_div.right
            row["target"] = text(f_div.left.left)
        elif not outs:
            row["form"] = "accumulator" if terms else "constant"
        else:
            forms = [shallowest(f) for f in outs]
            kinds = {f[0] for f in forms}
            if len(kinds) != 1:
                row["form"] = "mixed:" + ",".join(sorted(kinds))
            else:
                form, tau, cap, k = forms[0]
                row["form"] = form
                if cap is not None:
                    row["cap"] = text(cap)
                    row["cap_var"] = real.get(_cap_name(outs[0], s, comps, stocks))
                if form == "rate":
                    shared = [o for o, fs in rate_factors.items() if o != s and fs & rate_factors.get(s, set())]
                    if s not in {by_real.get(x) for x in conserved} and shared:
                        row["form"], row["coflow_of"] = "coflow", real[sorted(shared)[0]]
                    else:
                        kv = _evaluate(k, model, names, v)
                        row["state_dependent"] = bool(_calls(k) & stocks) or not np.allclose(kv, kv[0])
                        tau = ast.BinOp(left=ast.Constant(1.0), op=ast.Div(), right=k)
                        row["tau"] = "1 / (" + text(k) + ")"
        if row["form"] in ("drain", "drain_capped", "goal_seeking", "rate"):
            row["order"] = 1
            row["delay_type"] = "material" if real[s] in conserved else (
                "information" if row["form"] in ("drain", "goal_seeking") else "material")
            row["first_order_candidate"] = True
            if row["tau"] is None:
                row["tau"] = text(tau)
            tv = _evaluate(tau, model, names, v)
            row["tau_base"] = float(tv[0])
            row["tau_run"] = [float(np.min(tv)), float(np.max(tv))]
            tn = _call_name(_strip_float(tau))
            if tn in comps and comps[tn].ctype == "Constant":
                row["tau_var"] = real[tn]
                p = spec["parameters"].get(real[tn])
                if p:
                    row["tau_range"] = [p["low"], p["high"]]
            if row["state_dependent"] is None:
                row["state_dependent"] = bool(_calls(tau) - consts)
            for o in outs:
                row["downstream"] += [real[t] for t in sorted(stocks) if t != s
                                      and (1, o) in signed_terms(comps[t].flow, 1, never)]
            row["downstream"] = sorted(set(row["downstream"]))
        rows.append(row)
    return {"project": spec["model"]["name"], "model_file": spec["model"]["py"], "time_unit": spec["model"]["time_unit"],
            "time_step": spec["model"]["time_step"], "functions": functions, "stocks": rows}


def _fmt(x):
    if x is None:
        return ""
    if isinstance(x, float):
        return f"{x:.4g}"
    return str(x)


def write_markdown(rep, path):
    tu = rep["time_unit"]
    L = [f"# Delay audit: {rep['project']}", "",
         f"Generated by `engine/delay_audit.py` from `{rep['model_file']}` (structure) and one PySD base run (time-constant "
         f"values). Report only: the model is not changed. Euler integration, dt = {rep['time_step']} {tu}.", "",
         f"DELAY / SMOOTH / TREND functions in the model: {', '.join(rep['functions']) or 'none'}. Every delay below is "
         "an explicit stock (first order: one stock per delay). Forms and rules: see the docstring of "
         "`engine/delay_audit.py`.", "",
         f"| Stock | Form | Type | Order | Outflows | Time constant tau | tau at t=0 ({tu}) | tau over base run | "
         "Validated range | Notes |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rep["stocks"]:
        notes = []
        if r["cap"]:
            notes.append(f"capped by {r['cap']}")
        if r["coflow_of"]:
            notes.append(f"co-flow of {r['coflow_of']}")
        if r.get("target"):
            notes.append(f"adjusts toward {r['target']}")
        if r["state_dependent"]:
            notes.append("tau depends on model state")
        if r["downstream"]:
            notes.append("feeds " + ", ".join(r["downstream"]))
        run = f"{_fmt(r['tau_run'][0])}-{_fmt(r['tau_run'][1])}" if r["tau_run"] else ""
        L.append(f"| {r['stock']} | {r['form']} | {r['delay_type']} | {_fmt(r['order'])} | {', '.join(r['outflows'])} | "
                 f"{r['tau'] or ''} | {_fmt(r['tau_base'])} | {run} | "
                 f"{'' if not r['tau_range'] else _fmt(r['tau_range'][0]) + '-' + _fmt(r['tau_range'][1])} | "
                 f"{'; '.join(notes)} |")
    cands = [r["stock"] for r in rep["stocks"] if r["first_order_candidate"]]
    L += ["", f"**First-order delays (candidates for the fixed-delay check):** {', '.join(cands) or 'none'}. A "
          "first-order delay releases its contents exponentially: with residence time tau, 39% leave before tau/2 "
          "(1 - e^-0.5) and 13.5% are still inside after 2 tau (e^-2). A real process with a roughly fixed duration "
          "(a contract term, a fixed review cycle) releases almost nothing before that duration; modelling it as first "
          "order makes responses start too early and spread too long.", ""]
    head = "\n".join(L) + "\n"
    old = open(path, encoding="utf-8").read() if os.path.exists(path) else ""
    tail = old[old.index(MARKER):] if MARKER in old else MARKER + "\n"
    text = head + tail
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return text


def main(argv):
    argv, _ = sd_paths.extract_flag(argv)
    if len(argv) != 2:
        print(__doc__)
        return 2
    project = sd_paths.resolve_project(argv[1])
    problem = sd_paths.project_problem(project)
    if problem:
        print(f"ERROR: {problem}", file=sys.stderr)
        return 1
    rep = audit(project)
    with open(os.path.join(project, "delay_audit.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(rep, f, indent=1, sort_keys=True)
        f.write("\n")
    write_markdown(rep, os.path.join(project, "delay_audit.md"))
    print(f"{rep['project']}: {len(rep['stocks'])} stocks, "
          f"{sum(r['first_order_candidate'] for r in rep['stocks'])} first-order delays, functions: {rep['functions']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
