"""Export a PySD-translated model (.py) as a self-contained JavaScript Euler engine for the sd-explorer page.

Usage:  python -I engine/export_js.py projects/<model>/model/<name>.py [out.js]

The emitted script defines one global, `SDEngine`, with
  SDEngine.run(params, opts) -> {time: [...], series: {real name: [...]}}
  SDEngine.META               -> control values, stocks, parameters (real name -> base value), names
`params` maps parameter real names to numbers (unknown names throw); `opts` may set final_time, time_step, saveper.

It reproduces PySD 3.14.3's Model.run() step for step (pysd/py_backend/model.py _integrate, components.Time):
  state is initialised in dependency order; then, while t + dt*1e-5 < final_time: save the row if t is on the
  saveper grid, state = state + ddt * dt, t = t + dt; after the loop save once more if t is on the grid.
  Saved time is np.round(t, -int(log10(dt*1e-5))). Every binary operation is emitted fully parenthesised in
  Python's evaluation order, so JS performs the same IEEE-754 operations (Math.exp/Math.pow may differ from
  libm in the last bit; the parity test measures that).

Only these constructs are supported; anything else raises Unsupported (the build fails, nothing is guessed):
component calls, time(), control functions, numeric constants, + - * / ** unary -, comparisons, `and`/`or`/`not`
over comparisons, if_then_else(cond, lambda: a, lambda: b), float(x), np.maximum/minimum/exp/log/abs/sqrt/power/
floor/ceil/sin/cos/tan/arctan/tanh, and the Integ stateful (no SMOOTH/DELAY/lookups/data).
Ordering never depends on PySD's depends_on/other_deps dictionaries (their key order varies run to run):
edges come from the call sites in the equations, and every iteration is sorted.
"""
import ast
import hashlib
import heapq
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import loop_detector as ld  # noqa: E402  (read-only dependency)

CONTROL_JS = {"time": "t", "time_step": "DT", "final_time": "TF", "initial_time": "T0", "saveper": "SP"}
NP_JS = {"maximum": "Math.max", "minimum": "Math.min", "exp": "Math.exp", "log": "Math.log", "abs": "Math.abs",
         "sqrt": "Math.sqrt", "power": "Math.pow", "floor": "Math.floor", "ceil": "Math.ceil", "sin": "Math.sin",
         "cos": "Math.cos", "tan": "Math.tan", "arctan": "Math.atan", "tanh": "Math.tanh"}
NP_ARITY = {"maximum": 2, "minimum": 2, "power": 2}
BINOPS = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/"}
CMPOPS = {ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.Eq: "===", ast.NotEq: "!=="}
RPREC = 1e-5  # pysd components.Time.rprec


class Unsupported(Exception):
    """A model construct the exporter does not translate."""


def _bad(node, why):
    raise Unsupported(f"{why}: {ast.unparse(node)[:100]}")


def json_for_script(obj, **kw):
    """JSON for embedding inside an inline <script>, of any kind. Every '<' becomes \\u003c: the same string to a JSON
    or JavaScript reader, but it cannot open a '</script' or a '<!--<script' that the HTML tokenizer would act on,
    whatever a model names its variables. Used for the generated engine and for the page's data island."""
    return json.dumps(obj, **kw).replace("<", "\\u003c")


def _num(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    r = repr(float(value))
    return {"inf": "Infinity", "-inf": "-Infinity", "nan": "NaN"}.get(r, r)


def _is_bool(node):
    return (isinstance(node, (ast.Compare, ast.BoolOp))
            or (isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not))
            or (isinstance(node, ast.Constant) and isinstance(node.value, bool)))


def expr_js(node, names, stocks, ref=None):
    """JS text for one PySD expression. names: component py names; stocks: py names of Integ stocks.
    ref: optional py name -> JS reference (e.g. "V.x" for a value map); then time() reads ref("time") and any other
    control function is unsupported (the equation evaluator has no control values)."""
    def go(n):
        return expr_js(n, names, stocks, ref)

    def truth(n):
        return go(n) if _is_bool(n) else f"({go(n)} !== 0)"

    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return _num(node.value)
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.Pow):
            return f"Math.pow({go(node.left)}, {go(node.right)})"
        if type(node.op) not in BINOPS:
            _bad(node, "operator not supported")
        return f"({go(node.left)} {BINOPS[type(node.op)]} {go(node.right)})"
    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.USub):
            return f"(-{go(node.operand)})"
        if isinstance(node.op, ast.UAdd):
            return f"(+{go(node.operand)})"
        if isinstance(node.op, ast.Not):
            return f"(!{truth(node.operand)})"
        _bad(node, "unary operator not supported")
    if isinstance(node, ast.Compare):
        parts, left = [], node.left
        for op, right in zip(node.ops, node.comparators):
            if type(op) not in CMPOPS:
                _bad(node, "comparison not supported")
            parts.append(f"({go(left)} {CMPOPS[type(op)]} {go(right)})")
            left = right
        return parts[0] if len(parts) == 1 else "(" + " && ".join(parts) + ")"
    if isinstance(node, ast.BoolOp):
        if not all(_is_bool(v) for v in node.values):
            _bad(node, "and/or over non-boolean values returns an operand in Python")
        op = " && " if isinstance(node.op, ast.And) else " || "
        return "(" + op.join(go(v) for v in node.values) + ")"
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "np":
        if node.attr in ("nan", "inf"):
            return {"nan": "NaN", "inf": "Infinity"}[node.attr]
        _bad(node, "numpy attribute not supported")
    if isinstance(node, ast.Call):
        f = node.func
        if node.keywords or any(isinstance(a, ast.Starred) for a in node.args):
            _bad(node, "keyword or starred arguments not supported")
        if isinstance(f, ast.Name):
            if f.id in CONTROL_JS and not node.args:
                if ref is not None:
                    if f.id != "time":
                        _bad(node, "control value in an equation evaluated from a value map")
                    return ref("time")
                return CONTROL_JS[f.id]
            if f.id in names:
                if node.args:
                    _bad(node, "component called with arguments")
                return ref(f.id) if ref is not None else ("s_" if f.id in stocks else "v_") + f.id
            if f.id == "float" and len(node.args) == 1:
                return go(node.args[0])
            if f.id == "if_then_else" and len(node.args) == 3:
                a, b = node.args[1], node.args[2]
                if not (isinstance(a, ast.Lambda) and isinstance(b, ast.Lambda)):
                    _bad(node, "if_then_else branches must be lambdas")
                return f"({truth(node.args[0])} ? {go(a.body)} : {go(b.body)})"
            _bad(node, "unknown function")
        if (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "np"
                and f.attr in NP_JS):
            if len(node.args) != NP_ARITY.get(f.attr, 1):
                _bad(node, "wrong number of arguments")
            return f"{NP_JS[f.attr]}(" + ", ".join(go(a) for a in node.args) + ")"
        _bad(node, "call not supported")
    _bad(node, "construct not supported")


def _control_vars(tree):
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "_control_vars" and isinstance(node.value, ast.Dict)):
            lams = {}
            for k, v in zip(node.value.keys, node.value.values):
                if not isinstance(v, ast.Lambda):
                    _bad(v, "control variable must be a lambda")
                lams[ast.literal_eval(k)] = v.body

            def value(k, seen=()):
                e = lams[k]
                if k in seen:
                    _bad(e, f"control variable {k} refers to itself")
                if isinstance(e, ast.Call) and isinstance(e.func, ast.Name) and not e.args and e.func.id in lams:
                    return value(e.func.id, seen + (k,))        # Vensim's default SAVEPER = TIME STEP
                if isinstance(e, ast.Constant):
                    return e.value                              # a plain number, kept as written
                try:
                    return ast.literal_eval(e)                  # a signed number: INITIAL TIME = -10
                except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
                    _bad(e, "control variable must be a number or another control variable")
            out = {k: value(k) for k in lams}
            missing = [k for k in ("initial_time", "final_time", "time_step", "saveper") if k not in out]
            if missing:                      # the engine reads all four; a missing one was `undefined` in the page
                raise Unsupported(f"_control_vars has no {', '.join(missing)}")
            return out
    raise Unsupported("no _control_vars in model file")


def _toposort(nodes, deps, what):
    """Kahn's algorithm, ties broken by name (deterministic). deps: node -> set of nodes it needs."""
    need = {n: set(d) & set(nodes) for n, d in deps.items() if n in nodes}
    users = {n: set() for n in nodes}
    for n, ds in need.items():
        for d in ds:
            users[d].add(n)
    ready = [n for n in nodes if not need[n]]
    heapq.heapify(ready)
    order = []
    while ready:
        n = heapq.heappop(ready)
        order.append(n)
        for u in sorted(users[n]):
            need[u].discard(n)
            if not need[u]:
                heapq.heappush(ready, u)
    if len(order) != len(nodes):
        raise Unsupported(f"{what}: dependency cycle among {sorted(set(nodes) - set(order))[:8]}")
    return order


def load_ir(py_path):
    """Intermediate representation of a PySD model: control values, stocks, parameters, evaluation orders, JS."""
    text = open(py_path).read()
    tree = ast.parse(text)
    model = ld.parse_model(py_path)
    comps = {py: c for py, c in model.comps.items() if c.ctype != "Control" and py not in CONTROL_JS}
    names = set(comps)
    stocks = sorted(py for py, c in comps.items() if c.ctype == "Stateful")
    for py in stocks:
        c = comps[py]
        if c.flow is None or c.init is None:
            raise Unsupported(f"stateful '{c.name}' is not a plain INTEG (only Integ is supported)")
    for py, c in comps.items():
        if py not in stocks and c.expr is None:
            raise Unsupported(f"component '{c.name}' has no return expression")
    sset = set(stocks)
    js, calls = {}, {}
    for py in sorted(comps):
        c = comps[py]
        if py in sset:
            js[py] = {"flow": expr_js(c.flow, names, sset), "init": expr_js(c.init, names, sset)}
            calls[py] = {"flow": ld._calls(c.flow, names), "init": ld._calls(c.init, names)}
        else:
            js[py] = expr_js(c.expr, names, sset)
            calls[py] = ld._calls(c.expr, names)
    aux = sorted(n for n in comps if n not in sset)
    aux_order = _toposort(aux, {n: calls[n] - sset for n in aux}, "auxiliaries")
    init_deps = {n: (calls[n]["init"] if n in sset else calls[n]) for n in comps}
    init_order = _toposort(sorted(comps), init_deps, "initialisation")
    params = {}
    for py in aux:
        c = comps[py]
        if c.ctype == "Constant":
            if calls[py]:
                raise Unsupported(f"constant '{c.name}' depends on other components")
            params[c.name] = ast.literal_eval(c.expr) if isinstance(c.expr, ast.Constant) else None
            if not isinstance(params[c.name], (int, float)):
                raise Unsupported(f"constant '{c.name}' is not a number literal")
    return {
        "source": os.path.basename(py_path),
        "sha256": hashlib.sha256(text.encode()).hexdigest(),
        "control": _control_vars(tree),
        "names": {py: comps[py].name for py in sorted(comps)},
        "units": {py: comps[py].units for py in sorted(comps)},
        "stocks": [{"py": py, "name": comps[py].name, **js[py]} for py in stocks],
        "parameters": dict(sorted(params.items())),
        "param_py": {comps[py].name: py for py in aux if comps[py].ctype == "Constant"},
        "aux_order": aux_order,
        "init_order": init_order,
        "js": js,
    }


def emit_js(ir):
    """JavaScript source of the engine (deterministic for a given model file)."""
    names, js = ir["names"], ir["js"]
    stock_set = {s["py"] for s in ir["stocks"]}
    pp = ir["param_py"]

    def aux_line(py, indent):
        if names[py] in pp:
            return f"{indent}v_{py} = u_{py} ? p_{py} : {js[py]};"
        return f"{indent}v_{py} = {js[py]};"

    meta = {"source": ir["source"], "control": ir["control"], "names": names, "units": ir["units"],
            "stocks": [s["name"] for s in ir["stocks"]], "parameters": ir["parameters"]}
    L = []
    w = L.append
    w(f"// sd-explorer engine generated by engine/export_js.py from {ir['source']} sha256 {ir['sha256']}")
    w("// Euler integration reproducing PySD 3.14.3 Model.run(); see engine/export_js.py for the exact semantics.")
    w("var SDEngine = (function () {")
    w('  "use strict";')
    w("  var META = " + json_for_script(meta, sort_keys=True) + ";")
    w("  var PARAMS = Object.create(null);")
    w("  Object.keys(META.parameters).forEach(function (k) { PARAMS[k] = true; });")
    w("  function pymod(a, b) { var m = a % b; if (m !== 0 && ((m < 0) !== (b < 0))) { m += b; } return m; }")
    w("  function rint(x) { var r = Math.round(x); if (Math.abs(x % 1) === 0.5 && r % 2 !== 0) { r -= 1; } return r; }")
    w("  function has(o, k) { return Object.prototype.hasOwnProperty.call(o, k); }")
    w("  function run(P, opts) {")
    w("    P = P || {}; opts = opts || {};")
    w("    Object.keys(P).forEach(function (k) {")
    w('      if (!PARAMS[k]) { throw new Error("not a model parameter: " + k); }')
    w('      if (typeof P[k] !== "number") { throw new Error("parameter value must be a number: " + k); }')
    w("    });")
    w("    var T0 = META.control.initial_time;")
    w('    var TF = has(opts, "final_time") ? opts.final_time : META.control.final_time;')
    w('    var DT = has(opts, "time_step") ? opts.time_step : META.control.time_step;')
    w('    var SP = has(opts, "saveper") ? opts.saveper : META.control.saveper;')
    w(f"    var PREC = DT * {RPREC!r};")
    w(f"    var DEC = Math.trunc(Math.log10(DT * {RPREC!r})) * -1;")
    w("    var SCALE = Math.pow(10, DEC);")
    for py in sorted(names):
        if names[py] in pp:
            w(f"    var u_{py} = has(P, {json_for_script(names[py])}), p_{py} = u_{py} ? P[{json_for_script(names[py])}] : 0;")
    w("    var t = T0;")
    w("    var " + ", ".join(("s_" if py in stock_set else "v_") + py for py in sorted(names)) + ";")
    w("    // initial values, in dependency order")
    for py in ir["init_order"]:
        if py in stock_set:
            w(f"    s_{py} = {js[py]['init']};")
        else:
            w(aux_line(py, "    "))
    w("    function aux() {")
    for py in ir["aux_order"]:
        w(aux_line(py, "      "))
    w("    }")
    order = sorted(names, key=lambda p: names[p])
    w("    var out = {time: []};")
    w("    var series = {};")
    for py in order:
        w(f"    var o_{py} = series[{json_for_script(names[py])}] = [];")
    w("    function save() {")
    w("      out.time.push(rint(t * SCALE) / SCALE);")
    for py in order:
        w(f"      o_{py}.push({('s_' if py in stock_set else 'v_') + py});")
    w("    }")
    w("    function onGrid() { var d = t - T0; return pymod(d, SP) < PREC || pymod(-d, SP) < PREC; }")
    w("    aux();")
    w("    while (t + DT * " + repr(RPREC) + " < TF) {")
    w("      if (onGrid()) { save(); }")
    for s in ir["stocks"]:
        w(f"      var d_{s['py']} = {s['flow']};")
    for s in ir["stocks"]:
        w(f"      s_{s['py']} = s_{s['py']} + (d_{s['py']} * DT);")
    w("      t = t + DT;")
    w("      aux();")
    w("    }")
    w("    if (onGrid()) { save(); }")
    w("    out.series = series;")
    w("    return out;")
    w("  }")
    w("  return {META: META, run: run};")
    w("})();")
    return "\n".join(L) + "\n"


def emit_eqs(py_path):
    """JS defining SDEqs (py name -> function(V) evaluating that equation from a value map V of py names, plus
    V.time) and SDEQ_META (py name -> sorted inputs). A stock's equation is its net flow, an auxiliary's or flow's
    its own; constants have none. These are the equations engine/loop_detector.py scores links on (link_scores);
    an equation reading a control value other than time is null there (unscorable), as in loop_detector."""
    text = open(py_path).read()
    model = ld.parse_model(py_path)
    names = set(model.comps)
    control = ld.CONTROL
    eqs, meta = {}, {}
    for py in sorted(model.comps):
        c = model.comps[py]
        if c.ctype in ("Control", "Constant") or py in control:
            continue
        expr = c.flow if c.ctype == "Stateful" else c.expr
        if expr is None:
            continue
        meta[py] = sorted(ld._calls(expr, names) - control)
        try:
            eqs[py] = expr_js(expr, names, set(), ref=lambda p: "V." + p)
        except Unsupported:
            eqs[py] = None
    L = [f"// sd-explorer equations generated by engine/export_js.py from {os.path.basename(py_path)} sha256 "
         f"{hashlib.sha256(text.encode()).hexdigest()}",
         "// One function per equation, evaluated from a value map V (py names, plus V.time); used for link scores.",
         "var SDEQ_META = " + json_for_script(meta, sort_keys=True) + ";",
         "var SDEqs = {"]
    for py in sorted(eqs):
        L.append(f"  {py}: " + ("null," if eqs[py] is None else f"function (V) {{ return {eqs[py]}; }},"))
    L.append("};")
    return "\n".join(L) + "\n"


def main(argv):
    if len(argv) not in (2, 3):
        print(__doc__)
        return 2
    out = emit_js(load_ir(argv[1]))
    if len(argv) == 3:
        open(argv[2], "w").write(out)
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
