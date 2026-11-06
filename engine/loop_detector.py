"""Find feedback loops in a PySD-translated model and measure which loop dominates over time.

Usage:  python -I engine/loop_detector.py <model.mdl|model.py> [--final-time T] [--time-step DT] [--json out.json]

Structure comes from the PySD-generated .py (parsed with `ast`, never imported here):
every `@component.add` function gives an equation, every `Integ(...)` gives a stock.
Dominance uses the Loops-that-Matter (LTM) link-score idea (Schoenberg, Davidsen and
Eberlein, System Dynamics Review 2020; paper is pointer-only, method reimplemented from
its published definition; exact formula match with the paper is [unverified]):

  link score  LS(x->z) = |D_x z / D z| * sign(D_x z / D x)
     D z   = z(t) - z(t-dt)
     D_x z = f(x(t), other inputs at t-dt) - f(all inputs at t-dt)   (change in z due to x alone)
  For a stock, z is its net flow (sum of inflows minus outflows), so an inflow scores +|.|
  and an outflow -|.|.
  loop score  = product of the link scores around the loop
  relative    = loop score / sum over loops of |loop score|   (in [-1, 1]; sign = polarity)
  D z (or D x) within 1e-9 of the variable's scale -> link score 0 (no change, no attribution).

Only `Integ` stocks are scored. Loops that pass through other stateful objects (SMOOTH,
DELAY, ...) are still listed but marked unscored: write delays as explicit stocks instead.
"""
import ast
import json
import os
import sys
from dataclasses import dataclass, field

import numpy as np

CONTROL = {"time", "initial_time", "final_time", "time_step", "saveper"}
NP_FUNCS = {"minimum", "maximum", "exp", "log", "abs", "sqrt", "sin", "cos", "tan", "power",
            "floor", "ceil", "logical_and", "logical_or", "logical_not", "arctan", "tanh"}
REL_TOL = 1e-9


class Unsupported(Exception):
    """Expression construct the detector cannot evaluate."""


@dataclass
class Component:
    py: str
    name: str
    units: str
    ctype: str
    subtype: str
    expr: ast.AST = None          # aux/flow/constant: return expression
    flow: ast.AST = None          # Integ stock: net-flow expression
    init: ast.AST = None          # Integ stock: initial-value expression
    deps: set = field(default_factory=set)   # dynamic dependencies (edges into this var)
    scorable: bool = True


@dataclass
class Model:
    path: str
    comps: dict                   # py name -> Component

    @property
    def stocks(self):
        return [c for c in self.comps.values() if c.ctype == "Stateful"]

    def real(self, py):
        return self.comps[py].name if py in self.comps else py


def _calls(node, names):
    """Names of components called (as `name()`) anywhere inside node."""
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in names and not n.args:
            out.add(n.func.id)
    return out


def parse_model(py_path):
    """Parse a PySD-generated .py file into components and dependency sets."""
    tree = ast.parse(open(py_path).read())
    funcs, statefuls = {}, {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                if (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)
                        and dec.func.attr == "add"):
                    kw = {}
                    for k in dec.keywords:
                        try:
                            kw[k.arg] = ast.literal_eval(k.value)
                        except ValueError:
                            kw[k.arg] = None
                    ret = next((s.value for s in node.body if isinstance(s, ast.Return)), None)
                    funcs[node.name] = (kw, ret)
        elif (isinstance(node, ast.Assign) and len(node.targets) == 1
              and isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.Call)
              and isinstance(node.value.func, ast.Name)):
            statefuls[node.targets[0].id] = node.value
    names = set(funcs)
    comps = {}
    for py, (kw, ret) in funcs.items():
        c = Component(py=py, name=kw.get("name") or py, units=kw.get("units") or "",
                      ctype=kw.get("comp_type") or "", subtype=kw.get("comp_subtype") or "", expr=ret)
        if py in CONTROL:
            c.ctype = "Control"
        elif c.ctype == "Stateful":
            inner = _calls(ret, set(statefuls)) if ret is not None else set()
            obj = statefuls.get(next(iter(inner))) if inner else None
            if obj is not None and obj.func.id == "Integ" and len(obj.args) >= 2:
                c.flow, c.init = obj.args[0].body, obj.args[1].body
                c.deps = _calls(c.flow, names)
            else:
                c.scorable = False
                od = kw.get("other_deps") or {}
                c.deps = {d for v in od.values() for d in (v.get("step") or {}) if d in names}
        elif ret is not None:
            c.deps = _calls(ret, names)
        comps[py] = c
    return Model(path=py_path, comps=comps)


def graph(model):
    import networkx as nx
    g = nx.DiGraph()
    for c in model.comps.values():
        if c.ctype == "Control":
            continue
        g.add_node(c.py)
        for d in c.deps:
            if d not in CONTROL:
                g.add_edge(d, c.py)
    return g


def canonical(cycle):
    i = cycle.index(min(cycle))
    return tuple(cycle[i:] + cycle[:i])


def find_loops(model, max_loops=500):
    """All simple feedback loops, canonical rotation, sorted by length then names."""
    import networkx as nx
    loops, truncated = [], False
    for cyc in nx.simple_cycles(graph(model)):
        loops.append(canonical(list(cyc)))
        if len(loops) >= max_loops:
            truncated = True
            break
    return sorted(set(loops), key=lambda l: (len(l), l)), truncated


class _ToNumpy(ast.NodeTransformer):
    def __init__(self, names):
        self.names = names

    def visit_Call(self, node):
        f = node.func
        if isinstance(f, ast.Name) and f.id in self.names and not node.args:
            return ast.Subscript(value=ast.Name("v", ast.Load()), slice=ast.Constant(f.id), ctx=ast.Load())
        if isinstance(f, ast.Name) and f.id == "float" and len(node.args) == 1:
            return self.visit(node.args[0])
        if isinstance(f, ast.Name) and f.id == "if_then_else" and len(node.args) == 3:
            a, b = node.args[1], node.args[2]
            a = a.body if isinstance(a, ast.Lambda) else a
            b = b.body if isinstance(b, ast.Lambda) else b
            return ast.Call(func=ast.Attribute(ast.Name("np", ast.Load()), "where", ast.Load()),
                            args=[self.visit(node.args[0]), self.visit(a), self.visit(b)], keywords=[])
        if (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "np"
                and f.attr in NP_FUNCS):
            # checked before the arguments: model expressions only pass positional values
            if node.keywords:
                raise Unsupported(f"keyword arguments not allowed in np.{f.attr}: {ast.unparse(node)[:80]}")
            if any(isinstance(a, ast.Starred) for a in node.args):
                raise Unsupported(f"starred arguments not allowed in np.{f.attr}: {ast.unparse(node)[:80]}")
            node.args = [self.visit(a) for a in node.args]
            return node
        raise Unsupported(ast.unparse(node)[:80])

    def visit_Attribute(self, node):
        # np.<function> is handled in visit_Call; any other attribute access could reach object internals
        raise Unsupported(f"attribute access not allowed: {ast.unparse(node)[:80]}")

    def visit_Name(self, node):
        if node.id in ("np", "v"):
            return node
        raise Unsupported(f"bare name {node.id}")

    def visit_BoolOp(self, node):
        fn = "logical_and" if isinstance(node.op, ast.And) else "logical_or"
        vals = [self.visit(v) for v in node.values]
        out = vals[0]
        for v in vals[1:]:
            out = ast.Call(func=ast.Attribute(ast.Name("np", ast.Load()), fn, ast.Load()), args=[out, v], keywords=[])
        return out


def compile_expr(expr, names):
    """Turn a PySD return expression into f(v) where v maps py names to numpy arrays."""
    import copy
    body = _ToNumpy(names).visit(copy.deepcopy(expr))
    lam = ast.Expression(ast.Lambda(args=ast.arguments(posonlyargs=[], args=[ast.arg("v")], kwonlyargs=[],
                                                       kw_defaults=[], defaults=[]), body=body))
    ast.fix_missing_locations(lam)
    # our own AST: only v[...] lookups, operators and allowlisted np functions; no builtins
    return eval(compile(lam, "<sd-expr>", "eval"), {"__builtins__": {}, "np": np})  # noqa: S307


def values_from_frame(model, df):
    """Map a PySD run DataFrame (real-name columns, time index) to {py name: array}."""
    by_real = {c.name: py for py, c in model.comps.items()}
    v = {by_real[col]: np.asarray(df[col], dtype=float) for col in df.columns if col in by_real}
    v["time"] = np.asarray(df.index, dtype=float)
    return v


def _scale(a):
    return max(float(np.nanmax(np.abs(a))), 1e-300) if a.size else 1.0


def link_scores(model, v):
    """{(x, z): array of LTM link scores, length T-1} for every scorable edge; None if unscorable."""
    names = set(model.comps)
    out = {}
    for z in model.comps.values():
        if z.ctype in ("Control", "Constant") or not z.deps:
            continue
        expr = z.flow if z.ctype == "Stateful" else z.expr
        if not z.scorable or expr is None:
            for x in z.deps:
                out[(x, z.py)] = None
            continue
        try:
            f = compile_expr(expr, names)
            prev = {k: (a[:-1] if np.ndim(a) else a) for k, a in v.items()}
            base = np.broadcast_to(f(prev), prev["time"].shape).astype(float)
            full = np.broadcast_to(f(v), v["time"].shape).astype(float)
        except (Unsupported, KeyError):
            for x in z.deps:
                out[(x, z.py)] = None
            continue
        dz = full[1:] - full[:-1]
        dz_ok = np.abs(dz) > REL_TOL * _scale(full)
        for x in z.deps:
            if x in CONTROL:
                continue
            xa = v[x]
            dx = xa[1:] - xa[:-1]
            dx_ok = np.abs(dx) > REL_TOL * _scale(xa)
            moved = dict(prev)
            moved[x] = xa[1:]
            dxz = np.broadcast_to(f(moved), base.shape) - base
            with np.errstate(divide="ignore", invalid="ignore"):
                ls = np.where(dz_ok & dx_ok, np.abs(dxz / dz) * np.sign(dxz / dx), 0.0)
            out[(x, z.py)] = np.nan_to_num(ls)
    return out


def _sign_label(arr):
    s = np.sign(arr[arr != 0]) if arr is not None else np.array([])
    if s.size == 0:
        return "?"
    return "+" if np.all(s > 0) else "-" if np.all(s < 0) else "+/-"


def analyze(model, v, max_loops=500):
    """Loops, polarities and dominance timeline for one run (v from values_from_frame)."""
    loops, truncated = find_loops(model, max_loops)
    ls = link_scores(model, v)
    t = v["time"][1:]
    scores, info = [], []
    for i, lp in enumerate(loops):
        edges = list(zip(lp, lp[1:] + lp[:1]))
        arrs = [ls.get(e) for e in edges]
        scored = all(a is not None for a in arrs)
        signs = [_sign_label(a) for a in arrs]
        if all(s in "+-" for s in signs):
            polarity = "R" if signs.count("-") % 2 == 0 else "B"
        else:
            polarity = "mixed" if "+/-" in signs else "undetermined"
        sc = np.prod(np.vstack(arrs), axis=0) if scored else np.full(t.shape, np.nan)
        scores.append(sc)
        info.append({"id": f"L{i + 1}", "variables": [model.real(x) for x in lp], "py": list(lp),
                     "polarity": polarity, "link_signs": signs, "scored": scored})
    S = np.vstack(scores) if scores else np.zeros((0, t.size))
    tot = np.nansum(np.abs(S), axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        rel = np.where(tot > 0, S / tot, np.nan)
    periods = []
    if len(loops):
        dom = [None if np.all(np.isnan(rel[:, k])) or tot[k] == 0 else int(np.nanargmax(np.abs(rel[:, k])))
               for k in range(t.size)]
        start = 0
        for k in range(1, t.size + 1):
            if k == t.size or dom[k] != dom[start]:
                d = dom[start]
                seg = rel[d, start:k] if d is not None else np.array([np.nan])
                periods.append({"start": float(v["time"][start]), "end": float(t[k - 1]),
                                "loop": info[d]["id"] if d is not None else None,
                                "mean_relative_score": float(np.nanmean(seg)) if d is not None else None})
                start = k
    for i, d in enumerate(info):
        r = rel[i] if len(loops) else np.array([])
        d["mean_abs_relative_score"] = float(np.nanmean(np.abs(r))) if r.size and not np.all(np.isnan(r)) else None
        d["max_abs_relative_score"] = float(np.nanmax(np.abs(r))) if r.size and not np.all(np.isnan(r)) else None
    # Steps where at least one loop has a non-zero score. Where tot is 0 every relative score is NaN, so there is
    # no dominant loop and nothing for a loop-strength chart to draw at that step; 0 of n means the whole view is
    # empty. Reported so a caller can refuse to ship that silently (validate.py T8).
    return {"loops": info, "truncated": truncated, "dominance": periods,
            "scored_steps": int(np.count_nonzero(tot > 0)) if len(loops) else 0, "n_steps": int(t.size),
            "time": t.tolist(), "relative_scores": {d["id"]: rel[i].tolist() for i, d in enumerate(info)}}


def merge_short_periods(periods, min_length):
    """Fold dominance periods shorter than min_length into their predecessor (display only)."""
    out = []
    for p in periods:
        if out and (p["end"] - p["start"] < min_length or p["loop"] == out[-1]["loop"]):
            out[-1]["end"] = p["end"]
        else:
            out.append(dict(p))
    return out


def markdown(result, min_length=0.0):
    lines = ["| Loop | Polarity | Variables | Mean abs relative score |", "|---|---|---|---|"]
    for d in result["loops"]:
        m = d["mean_abs_relative_score"]
        lines.append(f"| {d['id']} | {d['polarity']} | {' -> '.join(d['variables'])} | "
                     f"{'n/a' if m is None else f'{m:.3f}'} |")
    lines += ["", "| From | To | Dominant loop | Mean relative score |", "|---|---|---|---|"]
    for p in merge_short_periods(result["dominance"], min_length):
        m = p["mean_relative_score"]
        lines.append(f"| {p['start']:g} | {p['end']:g} | {p['loop'] or 'none (no change)'} | "
                     f"{'' if m is None else f'{m:+.3f}'} |")
    return "\n".join(lines)


def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--final-time", type=float)
    ap.add_argument("--time-step", type=float)
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import validate  # worker-process runner (python -I, timeout)
    py = validate.translate(a.model) if a.model.endswith(".mdl") else a.model
    run = {"params": {}, "time_step": a.time_step, "final_time": a.final_time, "saveper_dt": True}
    df = validate.run_batch(py, [run])[0]
    model = parse_model(py)
    res = analyze(model, values_from_frame(model, df))
    print(markdown(res))
    if a.json:
        json.dump(res, open(a.json, "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1:])
