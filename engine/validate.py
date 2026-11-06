"""Validate a system dynamics model against its spec; results are released only if every test passes.

Usage:  python -I engine/validate.py projects/<model>/validation.toml [--n N] [--workers W]

Writes, next to the spec:
  validation_results.json   every test, its numbers and pass/fail, the sha256 of the model .mdl and .py it
                            validated and of the validation spec, and the sha256 of each result file below as
                            written by this run (always written, after the result files)
  validation_report.md      human-readable report (always written)
  mc_bands.csv, policy_results.csv, loop_dominance.json   results, written ONLY when all tests pass
Exit code 0 only if all tests pass.

Tests (thresholds from library/validation_tests.md):
  T0 translation   fresh PySD translation of the .mdl equals the committed .py, byte for byte except the key
                   order inside the dependency dictionaries (depends_on / other_deps), which PySD writes in a
                   per-process hash order (see same_translation)
  T1 units         dimensional consistency of every equation (0 mismatches, 0 unchecked)
  T1b MECE         every model variable in exactly one sector; no two variables share an equation
  T1c ranges       every parameter has base/low/high, low <= base <= high, [low, high] inside its domain,
                   loguniform low > 0; extreme and policy values stay inside the domain (no silent clipping);
                   [reference].set is exempt. Any T1c problem stops the run before any model is simulated.
  T3 extremes      each parameter at its domain bounds, 0, 0.1x and 10x base + spec expectations:
                   no NaN/inf, no stock below -1e-9 x scale, expectations hold
  T4 dt halving    max relative change of key outputs between dt and dt/2 < 1%, at base and at the
                   fastest corner of the parameter ranges
  T5 behavior      limit case (spec [reference].set, unclipped, optional own time_step) vs analytic reference: NRMSE <= nrmse_max, peak time within
                   tolerance, which may not exceed 5 steps of the reference run's own dt; base case shows the declared
                   behavior modes
  T6 conservation  conserved stock groups drift < 1e-6 relative, at base, corner and in every MC run
  T7 Monte Carlo   Latin hypercube, N >= 1000, 0 failed runs; percentile bands; Spearman importance;
                   policy ranking stability is REPORTED (T7b), not gating
  T8 loops         loops found by engine/loop_detector.py equal the declared CLD loops (same variables,
                   same polarity), all scorable; dominance timeline reported. Declared polarities must be R or B,
                   and a loop still undetermined (after any [loop_check]) fails. Polarity is read in the base run.
                   Optional [loop_check] set = {...}: ONLY loops with a zero link at base (a link that never
                   changes there, e.g. through an optional effect defaulting to 0) take their polarity from the
                   base run with those overrides; every other loop must match its declaration at base. Each
                   override must lie in that parameter's [low, high]; dominance is still from the true base run.
                   A base run in which no loop carries a score at any time step makes the loop-strength view of
                   every page built from the model empty; that fails unless dominance_empty_at_base gives the
                   reason, and a declaration that is not needed fails too

Every PySD run happens in a separate `python -I` worker process with a timeout (same pattern as
engine/translate_all.py); arrays come back through a temp .npz, status through a RESULT line.
"""
import ast
import hashlib
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import tomllib
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import generated_code_check  # noqa: E402
import loop_detector as ld  # noqa: E402

HERE = os.path.abspath(__file__)
MIN_MC_N = 1000
DT_TOL = 0.01
CONS_TOL = 1e-6
NEG_TOL = 1e-9
TIMEOUT_BASE_S = 60
TIMEOUT_PER_RUN_S = 2.0
KILL_GRACE_S = 5
PEAK_STEPS = 5          # T5: peak time within 5 steps of the reference run's own dt


# --------------------------------------------------------------------------- worker side

def worker(job_path):
    """Child-process entry point. Job JSON: {"kind": "run"|"translate", ...}; prints one RESULT line."""
    import warnings
    warnings.simplefilter("ignore")
    import pysd
    job = json.load(open(job_path))
    if job["kind"] == "translate":
        pysd.read_vensim(job["mdl"])
        print("RESULT" + json.dumps({"ok": True, "pysd_version": pysd.__version__}))
        return
    model = pysd.load(job["py"])
    # PySD keeps parameters and time settings set by one run() for the next one; every run here starts
    # from the model file's values: controls are always passed, touched parameters are reset.
    ctl = {"time_step": model.components.time_step(), "final_time": model.components.final_time(),
           "saveper": model.components.saveper()}
    defaults = {}
    arrays, errors, cols = {}, {}, {}
    for i, r in enumerate(job["runs"]):
        try:
            params = dict(r.get("params") or {})
            for k in params:
                if k not in defaults:
                    defaults[k] = float(model[k])
            for k, v in defaults.items():
                params.setdefault(k, v)
            kw = {"params": params, "progress": False}
            for k in ("time_step", "final_time", "saveper"):
                kw[k] = r[k] if r.get(k) is not None else ctl[k]
            if r.get("saveper_dt"):
                kw["saveper"] = kw["time_step"]
            if r.get("return_columns"):
                kw["return_columns"] = r["return_columns"]
            df = model.run(**kw)
            df = df[[c for c in df.columns if c not in ("FINAL TIME", "INITIAL TIME", "SAVEPER", "TIME STEP")]]
            arrays[f"run{i}"] = df.to_numpy(dtype=float)
            arrays[f"idx{i}"] = np.asarray(df.index, dtype=float)
            cols[str(i)] = list(df.columns)
        except Exception as e:  # noqa: BLE001 - report per run
            errors[i] = f"{type(e).__name__}: {e}"[:300]
    np.savez(job["out"], **arrays)
    print("RESULT" + json.dumps({"ok": True, "errors": errors, "columns": cols}))


def _kill_tree(p):
    """Kill the worker and every process it started (its own session/process group on POSIX)."""
    if hasattr(os, "killpg"):
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    else:
        # Windows: the venv's python.exe starts the real interpreter as a child, so p.kill() alone leaves it running.
        # taskkill /T ends the worker and every process it started.
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True, timeout=KILL_GRACE_S)
        except (OSError, subprocess.SubprocessError):
            pass
        p.kill()
    try:
        p.communicate(timeout=KILL_GRACE_S)
    except subprocess.TimeoutExpired:
        # a descendant that left the group still holds our pipes: stop reading, reap the worker
        for f in (p.stdout, p.stderr):
            f.close()
        p.wait()


def _spawn(job, timeout):
    with tempfile.TemporaryDirectory() as tmp:
        jp = os.path.join(tmp, "job.json")
        job = dict(job, out=os.path.join(tmp, "out.npz"))
        json.dump(job, open(jp, "w"))
        p = subprocess.Popen([sys.executable, "-I", HERE, "--worker", jp], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, start_new_session=True)
        try:
            stdout, stderr = p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_tree(p)
            return {"ok": False, "error": f"timeout after {timeout:.0f}s"}, None
        line = next((l for l in stdout.splitlines() if l.startswith("RESULT")), None)
        if line is None:
            tail = stderr.strip().splitlines()[-1] if stderr.strip() else "no output"
            return {"ok": False, "error": "worker crashed: " + tail[:300]}, None
        res = json.loads(line[6:])
        data = dict(np.load(job["out"])) if os.path.exists(job["out"]) else None
        return res, data


DEP_KEYWORDS = ("depends_on", "other_deps")


def _dependency_dicts(tree):
    """Dict literals passed as depends_on / other_deps to @component.add, in source order."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                f = getattr(dec, "func", None)
                if (isinstance(dec, ast.Call) and isinstance(f, ast.Attribute) and f.attr == "add"
                        and isinstance(f.value, ast.Name) and f.value.id == "component"):
                    out += [kw.value for kw in dec.keywords if kw.arg in DEP_KEYWORDS and isinstance(kw.value, ast.Dict)]
    return sorted(out, key=lambda n: (n.lineno, n.col_offset))


def _sorted_dump(node):
    """Dump of a dependency dict with its keys sorted at every level (other_deps nests dependency dicts)."""
    if not isinstance(node, ast.Dict) or None in node.keys:
        return ast.dump(node)
    return "{" + ",".join(sorted(f"{ast.dump(k)}:{_sorted_dump(v)}" for k, v in zip(node.keys, node.values))) + "}"


def _split_dependencies(text):
    """(bytes outside the dependency dicts, key-sorted dumps of the dependency dicts), located via the parsed code."""
    raw = text.encode()
    starts = [0]
    for line in raw.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    segs, deps, pos = [], [], 0
    for d in _dependency_dicts(ast.parse(text)):
        a, b = starts[d.lineno - 1] + d.col_offset, starts[d.end_lineno - 1] + d.end_col_offset
        segs.append(raw[pos:a])
        deps.append(_sorted_dump(d))
        pos = b
    segs.append(raw[pos:])
    return segs, deps


def same_translation(a, b):
    """T0 comparison of two PySD translations. Everything outside the dependency dictionaries (depends_on and
    other_deps of @component.add) must match byte for byte: equations, names, units, comments, other dicts.
    Inside them the same keys and counts must appear; only their order may differ, because PySD writes that
    order from Python's per-process string hash. Unparseable text falls back to byte equality."""
    try:
        return _split_dependencies(a) == _split_dependencies(b)
    except SyntaxError:
        return a == b


def translate(mdl, out_dir=None, timeout=120):
    """Translate an .mdl with PySD in a worker; returns the generated .py path (in out_dir or a new temp dir)."""
    out_dir = out_dir or tempfile.mkdtemp(prefix="sdv-")
    dst = os.path.join(out_dir, os.path.basename(mdl))
    if os.path.abspath(mdl) != os.path.abspath(dst):
        shutil.copy2(mdl, dst)
    res, _ = _spawn({"kind": "translate", "mdl": dst}, timeout)
    if not res.get("ok"):
        raise RuntimeError(f"translation failed: {res.get('error')}")
    py = os.path.splitext(dst)[0] + ".py"
    problems = generated_code_check.problems(py)
    if problems:
        raise RuntimeError("translation refused: the generated model file contains code that a PySD translation does "
                           "not produce (a model comment or name may be breaking out of its string): "
                           + "; ".join(problems[:3]))
    return py


CONTROL_COLUMNS = ("FINAL TIME", "INITIAL TIME", "SAVEPER", "TIME STEP")


def model_controls(py):
    """initial_time, final_time, time_step, saveper as written in the PySD model file (_control_vars)."""
    tree = ast.parse(open(py, encoding="utf-8").read())
    exprs = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_control_vars" for t in node.targets):
            exprs = {k.value: v.body for k, v in zip(node.value.keys, node.value.values) if isinstance(v, ast.Lambda)}
    out = {}

    def value(k, seen=()):
        e = exprs[k]
        if k in seen:
            raise ValueError(f"_control_vars: {k} refers to itself")
        if isinstance(e, ast.Call) and isinstance(e.func, ast.Name) and not e.args and e.func.id in exprs:
            return value(e.func.id, seen + (k,))       # e.g. "saveper": lambda: time_step()
        return float(ast.literal_eval(e))
    for k in ("initial_time", "final_time", "time_step", "saveper"):
        out[k] = value(k)
    return out


def model_columns(py):
    """The columns a full PySD run returns: every model component except the time controls."""
    return sorted(c.name for c in ld.parse_model(py).comps.values() if c.name not in CONTROL_COLUMNS + ("Time",))


def expected_times(initial, final, saveper, time_step=None):
    """The saved time grid of a run: initial, initial + saveper, ..., final (PySD saves the final step too)."""
    n = int(round((final - initial) / saveper))
    return initial + saveper * np.arange(n + 1)


def frame_problem(df, times, columns):
    """None when a result frame has exactly the expected time grid and every expected column; else the reason.
    The expectation comes from the model and the spec (expected_times, model_columns or the requested columns),
    never from the frame. An empty or missing frame is a problem."""
    if df is None:
        return "no result"
    idx = np.asarray(df.index, dtype=float)
    if len(idx) != len(times):
        return f"{len(idx)} time points, expected {len(times)}"
    if not np.allclose(idx, times, rtol=0.0, atol=1e-9 * max(1.0, float(np.max(np.abs(times))))):
        return "time grid differs from the expected one"
    missing = sorted(set(columns) - set(df.columns))
    if missing:
        return f"missing columns {missing[:5]}" + (" ..." if len(missing) > 5 else "")
    return None


def _place_chunk(out, start, expected, dfs, errors):
    """Put one chunk's frames into `out` without ever changing its length: a chunk that came back with a different
    number of frames than runs counts as failed (None for each of its runs)."""
    if len(dfs) != expected:
        errors.append(f"worker returned {len(dfs)} frames for {expected} runs (runs {start}-{start + expected - 1} counted as failed)")
        dfs = [None] * expected
    out[start:start + expected] = dfs


def run_batch(py, runs, workers=None, timeout_per_run=TIMEOUT_PER_RUN_S):
    """Run each spec in `runs` (dicts: params, time_step, final_time, saveper, saveper_dt,
    return_columns) in worker processes. Returns a list of DataFrames (None for failed runs)."""
    import pandas as pd
    workers = workers or min(os.cpu_count() or 2, 8)
    n = len(runs)
    size = max(1, math.ceil(n / workers))
    chunks = [(s, runs[s:s + size]) for s in range(0, n, size)]
    out = [None] * n

    def go(chunk):
        start, rs = chunk
        res, data = _spawn({"kind": "run", "py": os.path.abspath(py), "runs": rs},
                           TIMEOUT_BASE_S + timeout_per_run * len(rs))
        if not res.get("ok") or data is None:
            return start, [None] * len(rs), res.get("error")
        dfs = []
        for i in range(len(rs)):
            if f"run{i}" in data:
                dfs.append(pd.DataFrame(data[f"run{i}"], index=data[f"idx{i}"], columns=res["columns"][str(i)]))
            else:
                dfs.append(None)
        return start, dfs, res.get("errors")

    errors = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for (start, rs), (_, dfs, err) in zip(chunks, ex.map(go, chunks)):
            _place_chunk(out, start, len(rs), dfs, errors)
            if err:
                errors.append(err)
    run_batch.last_errors = errors
    return out


# --------------------------------------------------------------------------- units (T1)

class UnitError(Exception):
    pass


DMNL = {"dmnl", "dimensionless", "1", "fraction", "unitless"}


def parse_units(s):
    """'Firm/Month', '1/Month', 'Month/Year', '$/(Firm*Month)', 'Dmnl' -> {base: Fraction exponent}."""
    s = (s or "").strip()
    if not s:
        raise UnitError("missing units")
    if s.lower() in DMNL:
        return {}
    toks = re.findall(r"[A-Za-z_$%][A-Za-z0-9_$%]*|\d+(?:\.\d+)?|[*/^()-]", s)
    if "".join(toks) != re.sub(r"\s+", "", s):
        raise UnitError(f"cannot parse units '{s}'")
    pos = 0

    def peek():
        return toks[pos] if pos < len(toks) else None

    def take():
        nonlocal pos
        if pos >= len(toks):                           # a truncated unit ('Widgets*', '1/', 'Month^', '(Firm')
            raise UnitError(f"cannot parse units '{s}'")
        pos += 1
        return toks[pos - 1]

    def atom():
        t = take()
        if t == "(":
            u = expr()
            if take() != ")":
                raise UnitError(f"unbalanced '{s}'")
        elif re.fullmatch(r"\d+(?:\.\d+)?", t):
            u = {}
        else:
            u = {} if t.lower() in DMNL else {t: Fraction(1)}
        if peek() == "^":
            take()
            sign = -1 if peek() == "-" and take() else 1
            e = Fraction(take()) * sign
            u = {k: v * e for k, v in u.items()}
        return u

    def expr():
        u = atom()
        while peek() in ("*", "/"):
            op, v = take(), atom()
            u = umul(u, v if op == "*" else upow(v, -1))
        return u

    u = expr()
    if pos != len(toks):
        raise UnitError(f"cannot parse units '{s}'")
    return clean(u)


def clean(u):
    return {k: v for k, v in u.items() if v != 0}


def umul(a, b):
    c = Counter(a)
    for k, v in b.items():
        c[k] += v
    return clean(dict(c))


def upow(a, e):
    return clean({k: v * Fraction(e) for k, v in a.items()})


def ustr(u):
    if u is None:
        return "any"
    if not u:
        return "Dmnl"
    num = "*".join(k if v == 1 else f"{k}^{v}" for k, v in sorted(u.items()) if v > 0) or "1"
    den = "*".join(k if v == -1 else f"{k}^{-v}" for k, v in sorted(u.items()) if v < 0)
    return num + (f"/{den}" if den else "")


def _same(a, b, what):
    if a is None:
        return b
    if b is None or a == b:
        return a
    raise UnitError(f"{what}: {ustr(a)} vs {ustr(b)}")


def infer_units(node, units_of, time_unit):
    """Units of a PySD expression. None = polymorphic (literal 0). Raises UnitError."""
    rec = lambda n: infer_units(n, units_of, time_unit)  # noqa: E731
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return {}
        return None if node.value == 0 else {}
    if isinstance(node, ast.UnaryOp):
        return {} if isinstance(node.op, ast.Not) else rec(node.operand)
    if isinstance(node, ast.BinOp):
        a, b = rec(node.left), rec(node.right)
        if isinstance(node.op, (ast.Add, ast.Sub)):
            return _same(a, b, f"'{ast.unparse(node)[:60]}' adds")
        if isinstance(node.op, ast.Mult):
            return None if a is None or b is None else umul(a, b)
        if isinstance(node.op, ast.Div):
            if b is None:
                raise UnitError("division by literal 0")
            return None if a is None else umul(a, upow(b, -1))
        if isinstance(node.op, ast.Pow):
            return _pow(a, node.right, b)
        raise UnitError(f"operator {type(node.op).__name__}")
    if isinstance(node, ast.Compare):
        u = rec(node.left)
        for c in node.comparators:
            u = _same(u, rec(c), f"'{ast.unparse(node)[:60]}' compares")
        return {}
    if isinstance(node, ast.BoolOp):
        for v in node.values:
            _same(rec(v), {}, "logical operand")
        return {}
    if isinstance(node, ast.Lambda):
        return rec(node.body)
    if isinstance(node, ast.Call):
        f = node.func
        if isinstance(f, ast.Name):
            if f.id == "time" and not node.args:
                return parse_units(time_unit)
            if f.id in units_of and not node.args:
                return parse_units(units_of[f.id])
            if f.id == "float" and len(node.args) == 1:
                return rec(node.args[0])
            if f.id == "if_then_else" and len(node.args) == 3:
                _same(rec(node.args[0]), {}, "if condition")
                return _same(rec(node.args[1]), rec(node.args[2]), "if branches")
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "np":
            args = [rec(a) for a in node.args]
            if f.attr in ("minimum", "maximum"):
                return _same(args[0], args[1], f"np.{f.attr} arguments")
            if f.attr in ("abs", "floor", "ceil"):
                return args[0]
            if f.attr == "sqrt":
                return None if args[0] is None else upow(args[0], Fraction(1, 2))
            if f.attr == "power":
                return _pow(args[0], node.args[1], args[1])
            if f.attr in ("exp", "log", "sin", "cos", "tan", "tanh", "arctan"):
                _same(args[0], {}, f"np.{f.attr} argument must be Dmnl")
                return {}
            if f.attr in ("logical_and", "logical_or", "logical_not"):
                return {}
    raise UnitError(f"unchecked construct '{ast.unparse(node)[:60]}'")


def _pow(base, exp_node, exp_u):
    _same(exp_u, {}, "exponent must be Dmnl")
    if isinstance(exp_node, ast.Constant):
        return None if base is None else upow(base, Fraction(exp_node.value).limit_denominator(1000))
    if isinstance(exp_node, ast.UnaryOp) and isinstance(exp_node.operand, ast.Constant):
        return None if base is None else upow(base, -Fraction(exp_node.operand.value).limit_denominator(1000))
    _same(base, {}, "non-constant exponent needs a Dmnl base")
    return {}


def check_units(model, time_unit):
    """T1. Returns (n_checked, list of 'variable: problem')."""
    units_of = {py: c.units for py, c in model.comps.items()}
    problems, n = [], 0
    for c in model.comps.values():
        if c.ctype == "Control" or c.py == "time":
            continue
        n += 1
        try:
            own = parse_units(c.units)
            if c.ctype == "Stateful":
                if c.flow is None:
                    raise UnitError(f"stateful '{c.subtype}' not checked (write delays as explicit stocks)")
                fl = infer_units(c.flow, units_of, time_unit)
                if fl is not None:
                    _same(umul(fl, parse_units(time_unit)), own, "flow x time vs stock")
                _same(infer_units(c.init, units_of, time_unit), own, "initial value vs stock")
            elif c.ctype != "Constant" and c.expr is not None:
                _same(infer_units(c.expr, units_of, time_unit), own, "equation vs declared")
        except UnitError as e:
            problems.append(f"{c.name}: {e}")
    return n, problems


def check_mece(model, sectors):
    """T1b. Each model variable in exactly one sector; no duplicate equations."""
    names = {c.name for c in model.comps.values() if c.ctype != "Control" and c.py != "time"}
    seen = Counter(v for vs in sectors.values() for v in vs)
    problems = [f"'{v}' in {k} sectors" for v, k in seen.items() if k > 1]
    problems += [f"'{v}' in no sector" for v in sorted(names - set(seen))]
    problems += [f"'{v}' is not a model variable" for v in sorted(set(seen) - names)]
    eq = Counter()
    who = {}
    for c in model.comps.values():
        if c.ctype in ("Control", "Constant") or c.py == "time":
            continue
        key = ast.dump(c.flow if c.ctype == "Stateful" and c.flow is not None else c.expr)
        eq[key] += 1
        who.setdefault(key, []).append(c.name)
    problems += [f"identical equations: {who[k]}" for k, n in eq.items() if n > 1]
    return problems


# --------------------------------------------------------------------------- numeric helpers

def nrmse(sim, ref):
    sim, ref = np.asarray(sim, float), np.asarray(ref, float)
    rng = float(np.max(ref) - np.min(ref))
    return float(np.sqrt(np.mean((sim - ref) ** 2)) / rng) if rng > 0 else float("inf")


def classify_mode(y, tol=0.01):
    """'constant' | 'growth' | 'decline' | 's-curve' | 'peak' | 'oscillation' for a time series.
    s-curve: net rise, fastest rise strictly inside the run, final >= 90% of max (mild overshoot allowed).
    peak: interior maximum with both ends below 70% of it. oscillation: >= 2 interior maxima above
    10% of the range. growth/decline: monotone (within tol x range) with no interior inflection."""
    y = np.asarray(y, float)
    rng = float(y.max() - y.min())
    if rng <= 1e-12 * max(1.0, abs(y).max()):
        return "constant"
    d = np.diff(y)
    peaks = [i for i in range(1, len(y) - 1) if y[i] > y[i - 1] and y[i] >= y[i + 1] and y[i] - y.min() > 0.1 * rng]
    if len(peaks) >= 2:
        prom = [y[p] - min(y[peaks[0]:p + 1].min(), y[p:].min()) for p in peaks[1:]]
        if max(prom) > 0.1 * rng:
            return "oscillation"
    imax = int(np.argmax(y))
    if 0 < imax < len(y) - 1 and y[0] < 0.7 * y.max() and y[-1] < 0.7 * y.max():
        return "peak"
    if y[-1] > y[0]:
        k = int(np.argmax(d))
        if 0 < k < len(d) - 1 and y[-1] >= 0.9 * y.max() and d[k] > d[0] * 1.05 and d[k] > d[-1] * 1.05:
            return "s-curve"
        if np.all(d >= -tol * rng):
            return "growth"
    if y[-1] < y[0] and np.all(d <= tol * rng):
        return "decline"
    return "other"


def bass_cumulative(t, p, q, N):
    e = np.exp(-(p + q) * np.asarray(t, float))
    return N * (1 - e) / (1 + (q / p) * e)


def bass_peak_time(p, q):
    """t* = ln(q/p)/(p+q); only an interior peak when q > p (otherwise adoption is highest at t = 0)."""
    if not (p > 0 and q > p):
        raise ValueError(f"Bass peak time needs q > p (got p={p:g}, q={q:g})")
    return math.log(q / p) / (p + q)


def goal_seeking(t, G, y0, tau):
    """Closed form of a first-order approach to a goal: y' = (G - y)/tau, y(0) = y0."""
    return G + (y0 - G) * np.exp(-np.asarray(t, float) / tau)


ANALYTIC = {"bass": bass_cumulative, "goal_seeking": goal_seeking}


def peak_tolerance(ref, model_dt):
    """T5 rule: 5 steps of the reference run's OWN time step ([reference].time_step), else the model dt.
    A spec may set a tighter peak tolerance, never a looser one."""
    return PEAK_STEPS * float(ref.get("time_step", model_dt))


def stat(series, idx, s):
    y = np.asarray(series, float)
    t = np.asarray(idx, float)
    st = s["stat"]
    if st == "max":
        return float(y.max())
    if st == "min":
        return float(y.min())
    if st == "final":
        return float(y[-1])
    if st == "initial":
        return float(y[0])
    if st == "time_of_max":
        return float(t[int(np.argmax(y))])
    if st == "value_at":
        return float(np.interp(s["time"], t, y))
    if st == "time_to_reach":
        hit = np.nonzero(y >= s["value"])[0]
        return float(t[hit[0]]) if hit.size else float("inf")
    raise ValueError(f"unknown stat {st}")


OPS = {"<=": lambda a, b: a <= b, ">=": lambda a, b: a >= b, "<": lambda a, b: a < b,
       ">": lambda a, b: a > b, "==": lambda a, b: abs(a - b) <= 1e-9 * max(1, abs(b))}


def check_expect(df, e):
    """One expectation: {var, stat, op, value} or {var, stat: monotone_nondecreasing|monotone_nonincreasing}."""
    y = np.asarray(df[e["var"]], float)
    scale = max(1.0, float(np.abs(y).max()))
    if e["stat"] == "monotone_nondecreasing":
        return bool(np.all(np.diff(y) >= -NEG_TOL * scale)), float(np.diff(y).min())
    if e["stat"] == "monotone_nonincreasing":
        return bool(np.all(np.diff(y) <= NEG_TOL * scale)), float(np.diff(y).max())
    v = stat(y, df.index, e)
    return bool(OPS[e["op"]](v, e["value"])), v


# --------------------------------------------------------------------------- spec helpers

def load_spec(path):
    spec = tomllib.load(open(path, "rb"))
    base = os.path.dirname(os.path.abspath(path))
    spec["_dir"] = base
    real_base = os.path.realpath(base)
    for k in ("mdl", "py"):
        # the .py named here is imported (executed) by every run: an absolute path, a '..' or a symlink out of the
        # project would run a file the project does not contain. Keep the joined path as written, check where it lands.
        joined = os.path.join(base, spec["model"][k])
        landing = os.path.realpath(joined)
        if landing != real_base and os.path.commonpath([landing, real_base]) != real_base:
            raise ValueError(f"model.{k} must be inside the project folder, not {spec['model'][k]!r}")
        spec["model"][k + "_path"] = joined
    return spec


def check_parameters(spec):
    """T1c. Problems with the parameter table and with the values extremes and policies set; [] = pass.
    The [reference] limit case is exempt (documented in T5 as set unclipped, by design)."""
    params = spec.get("parameters", {})
    probs = []

    def domain(name):
        lo, hi = params[name].get("domain", [-math.inf, math.inf])
        return float(lo), float(hi)

    for k, v in params.items():
        missing = [key for key in ("base", "low", "high") if key not in v]
        probs += [f"{k}: missing {key}" for key in missing]
        if missing:
            continue
        b, lo, hi = v["base"], v["low"], v["high"]
        dlo, dhi = domain(k)
        if lo > hi:
            probs.append(f"{k}: low {lo:g} > high {hi:g}")
        if not lo <= b <= hi:
            probs.append(f"{k}: base {b:g} outside [low, high] = [{lo:g}, {hi:g}]")
        if lo < dlo or hi > dhi:
            probs.append(f"{k}: range [{lo:g}, {hi:g}] outside domain [{dlo:g}, {dhi:g}]")
        if v.get("distribution") == "loguniform" and lo <= 0:
            probs.append(f"{k}: loguniform needs low > 0")
    for e in spec.get("extreme", []):
        for k, x in e.get("set", {}).items():
            if k not in params:
                probs.append(f"extreme '{e['name']}': unknown parameter '{k}'")
            elif not domain(k)[0] <= x <= domain(k)[1]:
                probs.append(f"extreme '{e['name']}': {k} = {x:g} outside domain [{domain(k)[0]:g}, {domain(k)[1]:g}]")
    for k, x in (spec.get("loop_check") or {}).get("set", {}).items():
        if k not in params:
            probs.append(f"loop_check: unknown parameter '{k}'")
        elif "low" in params[k] and "high" in params[k] and not params[k]["low"] <= x <= params[k]["high"]:
            probs.append(f"loop_check: {k} = {x:g} outside [low, high] = [{params[k]['low']:g}, {params[k]['high']:g}]")
    for pol in spec.get("policies", []):
        for k, c in (pol.get("changes") or {}).items():
            if k not in params:
                probs.append(f"policy '{pol['name']}': unknown parameter '{k}'")
                continue
            dlo, dhi = domain(k)
            # mul/add/set are monotone in the input, so base, low and high bound every Monte Carlo sample
            for x in sorted({params[k][key] for key in ("base", "low", "high") if key in params[k]}):
                y = x * c.get("mul", 1.0) + c.get("add", 0.0)
                y = c.get("set", y)
                if not dlo <= y <= dhi:
                    probs.append(f"policy '{pol['name']}': {k} reaches {y:g} outside domain [{dlo:g}, {dhi:g}]")
    return probs


def base_params(spec):
    return {k: v["base"] for k, v in spec["parameters"].items()}


def clip(spec, name, x):
    lo, hi = spec["parameters"][name].get("domain", [-math.inf, math.inf])
    return float(min(max(x, lo), hi))


def corner_params(spec):
    """Fastest corner: time constants at their low end, rates at their high end."""
    p = base_params(spec)
    for k, v in spec["parameters"].items():
        if v.get("role") == "time_constant":
            p[k] = v["low"]
        elif v.get("role") == "rate":
            p[k] = v["high"]
    return p


def apply_changes(spec, params, changes):
    out = dict(params)
    for k, c in (changes or {}).items():
        x = out[k]
        if "mul" in c:
            x *= c["mul"]
        if "add" in c:
            x += c["add"]
        if "set" in c:
            x = c["set"]
        out[k] = clip(spec, k, x)
    return out


def lhs_samples(spec, n, seed):
    from scipy.stats import qmc, triang
    names = [k for k, v in spec["parameters"].items() if v.get("distribution", "uniform") != "fixed" and v["high"] > v["low"]]
    u = qmc.LatinHypercube(d=len(names), seed=seed).random(n)
    samples = []
    for row in u:
        p = base_params(spec)
        for j, k in enumerate(names):
            v = spec["parameters"][k]
            lo, hi, dist = v["low"], v["high"], v.get("distribution", "uniform")
            if dist == "uniform":
                x = lo + row[j] * (hi - lo)
            elif dist == "loguniform":
                x = math.exp(math.log(lo) + row[j] * (math.log(hi) - math.log(lo)))
            elif dist == "triangular":
                x = float(triang(c=(v["base"] - lo) / (hi - lo), loc=lo, scale=hi - lo).ppf(row[j]))
            else:
                raise ValueError(f"unknown distribution {dist} for {k}")
            p[k] = x
        samples.append(p)
    return names, samples


def group_labels(groups):
    """Display labels only: a repeated name becomes 'name (#k)'. Groups are tracked by position, never by label."""
    count = Counter(g["name"] for g in groups)
    seen = Counter()
    out = []
    for g in groups:
        seen[g["name"]] += 1
        out.append(g["name"] if count[g["name"]] == 1 else f"{g['name']} (#{seen[g['name']]})")
    return out


def group_drifts(df, groups):
    """[max |total(t) - total(0)| / |total(0)|] for each conserved stock group, in spec order."""
    out = []
    for g in groups:
        s = sum(np.asarray(df[x], float) for x in g["stocks"])
        out.append(float(np.max(np.abs(s - s[0])) / max(abs(s[0]), 1e-300)))
    return out


def conservation_drift(df, groups):
    return max(group_drifts(df, groups), default=0.0)


def _cycle_edges(variables):
    """Directed edges of a loop listed in causal order (any rotation gives the same set)."""
    v = list(variables)
    return frozenset(zip(v, v[1:] + v[:1]))


def match_loops(found, declared):
    """T8 matching on directed cycles. found: detector loops (id, polarity, variables in causal order);
    declared: spec loops (name, polarity, variables in causal order). Returns (problems, {found id: name|None})."""
    probs, decl = [], {}
    for d in declared:
        k = _cycle_edges(d["variables"])
        if k in decl:
            probs.append(f"declared loops '{decl[k]['name']}' and '{d['name']}' are the same cycle")
        else:
            decl[k] = d
    found_keys = {_cycle_edges(f["variables"]): f for f in found}
    found_sets = {frozenset(f["variables"]) for f in found}
    names = {}
    for k, f in found_keys.items():
        d = decl.get(k)
        names[f["id"]] = d["name"] if d else None
        if d is None:
            probs.append(f"undeclared loop {f['id']} ({f['polarity']}): {' -> '.join(f['variables'])}")
        elif d["polarity"] != f["polarity"]:
            probs.append(f"'{d['name']}' declared {d['polarity']}, detected {f['polarity']}")
    for k, d in decl.items():
        if k in found_keys:
            continue
        if frozenset(d["variables"]) in found_sets:
            probs.append(f"declared loop '{d['name']}' lists its variables against the model's causal direction")
        else:
            probs.append(f"declared loop '{d['name']}' not found in model")
    return probs, names


def dt_change(a, b, cols):
    """max over cols of max|a-b| / max|b| on the shared index."""
    common = a.index.intersection(b.index)
    out = {}
    for c in cols:
        x, y = np.asarray(a.loc[common, c], float), np.asarray(b.loc[common, c], float)
        out[c] = float(np.max(np.abs(x - y)) / max(float(np.max(np.abs(y))), 1e-300))
    return out


# --------------------------------------------------------------------------- the tests

def model_hashes(spec):
    """sha256 of the model files a run validates (the .mdl and its PySD .py), keyed by path relative to the spec, so
    later tools can tell whether the model changed after validation. Records only; checks nothing."""
    m = spec["model"]
    return {os.path.relpath(p, spec["_dir"]).replace(os.sep, "/"): hashlib.sha256(open(p, "rb").read()).hexdigest()
            for p in (m["mdl_path"], m["py_path"])}


def run_all(spec_path, n=None, workers=None):
    spec = load_spec(spec_path)
    m = spec["model"]
    py, mdl = m["py_path"], m["mdl_path"]
    R = {"model": m["name"], "model_files": model_hashes(spec),
         "spec_files": {os.path.basename(spec_path): hashlib.sha256(open(spec_path, "rb").read()).hexdigest()}, "tests": {}}
    T = R["tests"]
    key = m["key_outputs"]
    save = m.get("saveper", 1)
    time_kw = {"final_time": m["final_time"], "time_step": m["time_step"], "saveper": save}

    # T0 translation
    with tempfile.TemporaryDirectory() as tmp:
        try:
            fresh = open(translate(mdl, tmp)).read()
            same = same_translation(fresh, open(py).read())
            T["T0_translation"] = {"pass": same, "comparison": "dependency-key order normalized",
                                   "detail": "fresh PySD translation identical to committed .py (dependency-key order normalized)"
                                   if same else "committed .py differs from a fresh translation of the .mdl "
                                                "(compared with dependency-key order normalized)"}
        except Exception as e:  # noqa: BLE001
            T["T0_translation"] = {"pass": False, "comparison": "dependency-key order normalized", "detail": str(e)[:300]}
    model = ld.parse_model(py)

    # T1 units, T1b MECE
    n_chk, probs = check_units(model, m["time_unit"])
    T["T1_units"] = {"pass": not probs, "checked": n_chk, "problems": probs}
    mp = check_mece(model, spec.get("sectors", {}))
    T["T1b_mece"] = {"pass": not mp, "problems": mp, "sectors": {k: len(v) for k, v in spec.get("sectors", {}).items()}}
    pp = check_parameters(spec)
    T["T1c_parameter_ranges"] = {"pass": not pp, "problems": pp, "exempt": "reference limit case (T5)"}
    if pp:
        R["fatal"] = "parameter specification invalid (see T1c_parameter_ranges); no model runs performed"
        R["all_pass"] = False
        return spec, R, None
    if not T["T0_translation"]["pass"]:
        # Every run below imports the committed .py (pysd.load executes it). T0 having failed means that file is not
        # what PySD writes from the .mdl, so it is not run at all: reporting a mismatch after executing it is too late.
        # The tests above read it with ast only, so their problems are still reported.
        R["fatal"] = ("the committed model .py is not a fresh PySD translation of the .mdl "
                      "(see T0_translation); no model runs performed")
        R["all_pass"] = False
        return spec, R, None

    base = base_params(spec)
    corner = corner_params(spec)
    dt = m["time_step"]
    stocks = [c.name for c in model.stocks]
    groups = spec.get("conservation", [])

    # one batch for the deterministic runs
    runs = {
        "base": dict(params=base, **time_kw),
        "base_half": dict(params=base, **dict(time_kw, time_step=dt / 2)),
        "base_quarter": dict(params=base, **dict(time_kw, time_step=dt / 4)),
        "corner": dict(params=corner, **time_kw),
        "corner_half": dict(params=corner, **dict(time_kw, time_step=dt / 2)),
        "base_fine": dict(params=base, final_time=m["final_time"], time_step=dt, saveper_dt=True),
    }
    ext_cases = []
    for k, v in spec["parameters"].items():
        lo, hi = v.get("domain", [-math.inf, math.inf])
        cand = {lo, hi, 0.0, 0.1 * v["base"], 10 * v["base"]}
        for x in sorted(c for c in cand if math.isfinite(c)):
            x = clip(spec, k, x)
            ext_cases.append((f"{k} = {x:g}", dict(base, **{k: x}), None))
    for e in spec.get("extreme", []):
        ext_cases.append((e["name"], apply_changes(spec, base, {k: {"set": v} for k, v in e["set"].items()}), e["expect"]))
    loop_set = (spec.get("loop_check") or {}).get("set", {})
    if loop_set:
        # T8 polarity run: base plus the declared overrides (checked by T1c to lie in each [low, high])
        runs["loop_check"] = dict(params=dict(base, **loop_set), final_time=m["final_time"], time_step=dt, saveper_dt=True)
    ref = spec.get("reference")
    if ref:
        # limit case: set exactly as written (no domain clipping) and optionally with its own finer
        # time step, so time constants can be taken much closer to 0 than the base dt allows
        rp = dict(base, **ref.get("set", {}))
        runs["reference"] = dict(params=rp, final_time=m["final_time"], time_step=ref.get("time_step", dt), saveper_dt=True)
    names = list(runs)
    dfs = run_batch(py, [runs[k] for k in names] + [dict(params=p, **time_kw) for _, p, _ in ext_cases], workers)
    D = dict(zip(names, dfs[:len(names)]))
    E = dfs[len(names):]
    missing = [k for k, d in D.items() if d is None]
    if missing:
        R["fatal"] = f"deterministic runs failed: {missing}; worker errors: {run_batch.last_errors}"
        return spec, R, None

    # T3 extremes
    scale = {s: max(1.0, float(np.abs(D["base"][s]).max())) for s in stocks}
    fails, rows = [], []
    if len(E) != len(ext_cases):   # every extreme case must come back; zip() below would skip the missing ones
        fails.append(f"T3: {len(E)} results for {len(ext_cases)} extreme cases")
    ctl = model_controls(py)
    grid, all_cols = expected_times(ctl["initial_time"], m["final_time"], save, m["time_step"]), model_columns(py)
    for (label, _, expect), df in zip(ext_cases, E):
        if df is None:
            fails.append(f"{label}: run failed")
            continue
        prob = frame_problem(df, grid, all_cols)     # every case must hold the whole grid and every column
        if prob:
            fails.append(f"{label}: incomplete run ({prob})")
            continue
        vals = df.to_numpy(float)
        if not np.all(np.isfinite(vals)):
            fails.append(f"{label}: NaN/inf")
        for s in stocks:
            mn = float(df[s].min())
            if mn < -NEG_TOL * scale[s]:
                fails.append(f"{label}: {s} min {mn:.3g}")
        for e in expect or []:
            ok, v = check_expect(df, e)
            rows.append({"case": label, "check": f"{e['var']} {e['stat']} {e.get('op', '')} {e.get('value', '')}".strip(),
                         "value": v, "pass": ok})
            if not ok:
                fails.append(f"{label}: {e['var']} {e['stat']} = {v:.4g} fails {e.get('op', '')} {e.get('value', '')}")
    T["T3_extremes"] = {"pass": not fails, "cases": len(ext_cases), "failures": fails, "expectations": rows}

    # T4 dt halving
    ch_base = dt_change(D["base"], D["base_half"], key)
    ch_corner = dt_change(D["corner"], D["corner_half"], key)
    e1 = dt_change(D["base"], D["base_quarter"], key)
    e2 = dt_change(D["base_half"], D["base_quarter"], key)
    ratio = {c: (e1[c] / e2[c] if e2[c] > 0 else None) for c in key}
    worst = max(max(ch_base.values()), max(ch_corner.values()))
    t4_probs = [f"{c} ({case}): max relative change {x:.3g} between dt={dt:g} and dt/2 exceeds {DT_TOL:g}"
                for case, ch in (("base", ch_base), ("corner", ch_corner)) for c, x in ch.items() if not x < DT_TOL]
    T["T4_dt_halving"] = {"pass": worst < DT_TOL, "problems": t4_probs, "dt": dt, "max_rel_change": worst, "base": ch_base,
                          "corner": ch_corner, "euler_error_ratio_dt_vs_dt2": ratio,
                          "corner_params": {k: corner[k] for k, v in spec["parameters"].items() if v.get("role") in ("time_constant", "rate")}}

    # T6 conservation (MC runs added below)
    by_run = {k: group_drifts(D[k], groups) for k in ("base", "corner", "base_fine")}
    cons = {k: max(v, default=0.0) for k, v in by_run.items()}

    # T5 behavior reproduction
    if ref:
        df = D["reference"]
        sim = sum(np.asarray(df[c], float) for c in ref["compare"])
        args = {}
        for a, v in ref["args"].items():
            args[a] = v if isinstance(v, (int, float)) else rp[v["param"]] * v.get("factor", 1.0)
        refser = ANALYTIC[ref["function"]](df.index, **args)
        err = nrmse(sim, refser)
        pk = ref.get("peak")
        pk_res = None
        if pk:
            t_sim = float(df.index[int(np.argmax(np.asarray(df[pk["var"]], float)))])
            rule = peak_tolerance(ref, dt)
            try:
                if pk["tolerance"] > rule * (1 + 1e-9):
                    raise ValueError(f"peak tolerance {pk['tolerance']:g} exceeds {PEAK_STEPS} x reference dt = {rule:g}")
                t_ref = bass_peak_time(args["p"], args["q"])
                pk_res = {"var": pk["var"], "sim": t_sim, "analytic": t_ref, "error": abs(t_sim - t_ref),
                          "tolerance": pk["tolerance"], "rule": rule, "pass": abs(t_sim - t_ref) <= pk["tolerance"]}
            except ValueError as e:
                pk_res = {"var": pk["var"], "pass": False, "error": str(e)}
        modes = []
        for md in ref.get("modes", []):
            got = classify_mode(D["base_fine"][md["var"]])
            modes.append({"var": md["var"], "expected": md["mode"], "got": got, "pass": got == md["mode"]})
        ok = err <= ref["nrmse_max"] and (pk_res is None or pk_res["pass"]) and all(x["pass"] for x in modes)
        T["T5_behavior"] = {"pass": ok, "nrmse": err, "nrmse_max": ref["nrmse_max"], "compare": ref["compare"],
                            "reference": f"{ref['function']}({args})", "limit_case": ref.get("set", {}),
                            "peak": pk_res, "modes": modes}
    else:
        T["T5_behavior"] = {"pass": False, "detail": "no [reference] in spec"}

    # T7 Monte Carlo
    mc = spec["montecarlo"]
    n = n or mc["n"]
    seed = mc.get("seed")
    results = None
    if not isinstance(seed, int) or isinstance(seed, bool):
        T["T7_monte_carlo"] = {"pass": False, "detail": "montecarlo.seed must be an integer"}
    elif n < MIN_MC_N:
        T["T7_monte_carlo"] = {"pass": False, "detail": f"N = {n} < {MIN_MC_N}"}
    else:
        results = monte_carlo(spec, py, n, seed, key, stocks, groups, time_kw, workers)
        cons["monte_carlo_max"] = results["max_drift"]
        by_run["monte_carlo_max"] = results["group_drift"]
        T["T7_monte_carlo"] = {"pass": results["failed"] == 0, "n": n, "seed": seed, "failed_runs": results["failed"],
                               "sampled_parameters": results["names"], "metrics": results["metric_pct"],
                               "spearman": results["spearman"]}
        if not results["bands"]:
            T["T7_monte_carlo"]["detail"] = "no successful Monte Carlo runs"
        if "policy" in results:
            T["T7b_policy_ranking"] = dict(results["policy"], gating=False)
    labels = group_labels(groups)
    t6_probs = [f"group '{g}': max relative drift {x:.3g} > {CONS_TOL:g} in {run}"
                for run, gd in by_run.items() for g, x in zip(labels, gd) if not x < CONS_TOL]
    T["T6_conservation"] = {"pass": all(v < CONS_TOL for v in cons.values()), "problems": t6_probs, "max_rel_drift": cons,
                            "groups": groups}

    # T8 loops
    try:
        la = ld.analyze(model, ld.values_from_frame(model, D["base_fine"]))
        pa = ld.analyze(model, ld.values_from_frame(model, D["loop_check"])) if loop_set else la
        if [d["py"] for d in pa["loops"]] != [d["py"] for d in la["loops"]]:
            raise RuntimeError("loop enumeration differs between the base and loop_check runs")
        # A loop whose polarity can be read in the base run keeps its base polarity and must match its declaration
        # there. [loop_check] decides only loops with a zero link at base ("?": the link never changed in that run).
        from_check = []
        for d, q in zip(la["loops"], pa["loops"]):
            if loop_set and "?" in d["link_signs"]:
                d["polarity"], d["link_signs"] = q["polarity"], q["link_signs"]
                from_check.append(d["id"])
            d["polarity_source"] = "loop_check" if d["id"] in from_check else "base"
        probs, names = match_loops(la["loops"], spec.get("loops", []))
        # a declaration must state a polarity (R or B); a loop that stays undetermined is never accepted, even if
        # declared "undetermined" (string equality alone let that pass)
        probs += [f"'{d.get('name')}' declared polarity {d.get('polarity')!r}: must be R or B"
                  for d in spec.get("loops", []) if d.get("polarity") not in ("R", "B")]
        where = "after the [loop_check] override" if loop_set else "in the base run (no [loop_check])"
        probs += [f"'{names[d['id']]}' polarity {'still ' if loop_set else ''}undetermined {where}"
                  for d in la["loops"] if d["polarity"] == "undetermined" and names[d["id"]]]
        probs += [f"loop {d['id']} unscored" for d in la["loops"] if not d["scored"]]
        if la["truncated"]:
            probs.append("loop enumeration truncated")
        # A loop-strength view with nothing in it. Where no loop has a non-zero score at a step, every relative score
        # there is NaN: no dominant loop, and nothing for the explorer's loop-strength chart to draw. 0 of n steps
        # means the whole view is empty on every page built from this model. That can be a deliberate base case (every
        # optional feedback switched off), so it is allowed - but only when the reason is declared, never silently.
        empty = spec.get("dominance_empty_at_base")
        declared = isinstance(empty, str) and empty.strip() != ""
        if empty is not None and not declared:
            probs.append("dominance_empty_at_base must be a non-empty string giving the reason")
        if la["n_steps"] and not la["scored_steps"] and not declared:
            probs.append(f"no loop has a non-zero score at any of the {la['n_steps']} time steps of the base run, so "
                         "the loop-strength view of every page built from this model is empty. Change the base case, "
                         "or state why in dominance_empty_at_base.")
        if declared and la["scored_steps"]:
            probs.append(f"dominance_empty_at_base is declared but {la['scored_steps']} of {la['n_steps']} base-run "
                         "time steps do carry a loop score: remove the declaration.")
        for d in la["loops"]:
            d["name"] = names[d["id"]]
        T["T8_loops"] = {"pass": not probs, "n_loops": len(la["loops"]), "problems": probs,
                         "scored_steps": la["scored_steps"], "n_steps": la["n_steps"],
                         "dominance_empty_at_base": empty if declared else None,
                         "polarity_run": dict(loop_set) if loop_set else "base",
                         "polarity_from_loop_check": [d["name"] or d["id"] for d in la["loops"] if d["id"] in from_check],
                         "loops": [{k: d[k] for k in ("id", "name", "polarity", "polarity_source", "variables",
                                                      "mean_abs_relative_score", "max_abs_relative_score")} for d in la["loops"]],
                         "dominance": ld.merge_short_periods(la["dominance"], spec.get("dominance_min_period", 1.0))}
        R["_loop_analysis"] = la
    except Exception as e:  # noqa: BLE001
        T["T8_loops"] = {"pass": False, "problems": [f"{type(e).__name__}: {e}"]}

    R["all_pass"] = all(t["pass"] for k, t in T.items() if t.get("gating", True))
    return spec, R, results


def monte_carlo(spec, py, n, seed, key, stocks, groups, time_kw, workers):
    names, samples = lhs_samples(spec, n, seed)
    mc = spec["montecarlo"]
    metrics = mc.get("metrics", [])
    cols = sorted(set(key) | {s for g in groups for s in g["stocks"]} | {mt["var"] for mt in metrics})
    pol = spec.get("policies", [])
    scen = pol if pol else [{"name": "base", "changes": {}}]
    all_runs = []
    for sc in scen:
        all_runs += [dict(params=apply_changes(spec, p, sc.get("changes")), return_columns=cols, **time_kw) for p in samples]
    dfs = run_batch(py, all_runs, workers)
    ctl = model_controls(py)
    grid = expected_times(ctl["initial_time"], time_kw["final_time"], time_kw["saveper"], time_kw["time_step"])
    out = {"names": names, "samples": samples, "failed": 0, "max_drift": 0.0,
           "group_drift": [0.0] * len(groups)}
    per = {}
    for i, sc in enumerate(scen):
        part = dfs[i * n:(i + 1) * n]
        # a run that crashed or produced NaN/inf is a failed run and is excluded from every summary
        part = [d if d is not None and frame_problem(d, grid, cols) is None and np.all(np.isfinite(d.to_numpy(float)))
                else None for d in part]          # an incomplete run (wrong grid, missing columns, empty) is a failed run
        out["failed"] += sum(d is None for d in part)
        good = [d for d in part if d is not None]
        for d in good:
            out["group_drift"] = [max(a, b) for a, b in zip(out["group_drift"], group_drifts(d, groups))]
        out["max_drift"] = max(out["group_drift"], default=0.0)
        per[sc["name"]] = part
    base_name = scen[0]["name"]
    good = [d for d in per[base_name] if d is not None]
    if not good:  # nothing to summarise; T7 fails on out["failed"]
        out.update(bands={}, band_time=[], metric_pct={}, spearman={})
        return out
    idx = good[0].index
    q = [5, 25, 50, 75, 95]
    bands = {}
    for c in key:
        arr = np.vstack([np.asarray(d[c], float) for d in good])
        bands[c] = {f"P{x}": np.percentile(arr, x, axis=0).tolist() for x in q}
    out["bands"], out["band_time"] = bands, idx.tolist()
    mvals = {mt["name"]: np.array([stat(d[mt["var"]], d.index, mt) if d is not None else np.nan for d in per[base_name]])
             for mt in metrics}
    out["metric_pct"] = {k: {f"P{x}": float(np.nanpercentile(v, x)) for x in q} for k, v in mvals.items()}
    from scipy.stats import spearmanr
    sp = {}
    for k, v in mvals.items():
        sp[k] = {}
        for nm in names:
            x = np.array([s[nm] for s in samples])
            ok = np.isfinite(v)
            r = spearmanr(x[ok], v[ok]).statistic if ok.sum() > 2 and np.std(v[ok]) > 0 else float("nan")
            sp[k][nm] = float(r)
    out["spearman"] = sp
    if pol:
        obj = next(mt for mt in metrics if mt["name"] == spec["policy"]["objective"])
        sign = 1 if spec["policy"].get("maximize", True) else -1
        V = np.array([[stat(d[obj["var"]], d.index, obj) if d is not None else np.nan for d in per[sc["name"]]]
                      for sc in scen])  # scenarios x samples
        ranks = [tuple(np.argsort(-sign * V[:, j], kind="stable")) for j in range(n)]
        modal, cnt = Counter(ranks).most_common(1)[0]
        best = Counter(r[0] for r in ranks).most_common(1)[0]
        delta = V - V[0]
        out["policy"] = {
            "objective": obj["name"], "maximize": sign > 0,
            "modal_ranking": [scen[i]["name"] for i in modal],
            "full_ranking_stability": cnt / n,
            "best_policy": scen[best[0]]["name"], "best_policy_stability": best[1] / n,
            "pass": cnt / n >= 0.95,
            "scenarios": {sc["name"]: {"P5": float(np.nanpercentile(V[i], 5)), "P50": float(np.nanpercentile(V[i], 50)),
                                        "P95": float(np.nanpercentile(V[i], 95)),
                                        "gain_vs_base_P5": float(np.nanpercentile(delta[i], 5)),
                                        "gain_vs_base_P50": float(np.nanpercentile(delta[i], 50)),
                                        "gain_vs_base_P95": float(np.nanpercentile(delta[i], 95)),
                                        "changes": sc.get("changes", {})} for i, sc in enumerate(scen)},
        }
    return out


# --------------------------------------------------------------------------- reporting

def fmt(x, d=4):
    if x is None:
        return "n/a"
    if isinstance(x, float):
        if math.isinf(x):
            return "inf"
        return f"{x:.{d}g}"
    return str(x)


RELEASE_FILES = ("mc_bands.csv", "policy_results.csv", "loop_dominance.json")


def write_outputs(spec, R, results):
    d = spec["_dir"]
    la = R.pop("_loop_analysis", None)
    T = R["tests"]
    L = [f"# Validation report: {R['model']}", "",
         f"Generated by `engine/validate.py`. Overall: **{'PASS' if R.get('all_pass') else 'FAIL'}**. "
         "Numbers below are copied from `validation_results.json` by the script.", ""]
    if "fatal" in R:
        L += ["**Fatal:** " + R["fatal"], ""]
    L += ["| Test | Result | Key number |", "|---|---|---|"]
    keynum = {
        "T0_translation": lambda t: t.get("detail", ""),
        "T1_units": lambda t: f"{t['checked']} variables, {len(t['problems'])} problems",
        "T1b_mece": lambda t: f"{len(t['problems'])} problems",
        "T1c_parameter_ranges": lambda t: f"{len(t['problems'])} problems",
        "T3_extremes": lambda t: f"{t['cases']} cases, {len(t['failures'])} failures",
        "T4_dt_halving": lambda t: f"max rel. change {fmt(t['max_rel_change'])} (limit {DT_TOL})",
        "T5_behavior": lambda t: f"NRMSE {fmt(t.get('nrmse'))} (limit {t.get('nrmse_max')})",
        "T6_conservation": lambda t: f"max rel. drift {fmt(max(t['max_rel_drift'].values()))} (limit {CONS_TOL})",
        "T7_monte_carlo": lambda t: f"N = {t.get('n')}, failed runs {t.get('failed_runs')}" if "n" in t else t.get("detail", ""),
        "T7b_policy_ranking": lambda t: f"full ranking stable in {fmt(t['full_ranking_stability'] * 100, 3)}% of runs; "
                                        f"best policy stable in {fmt(t['best_policy_stability'] * 100, 3)}% (reported, not gating)",
        "T8_loops": lambda t: f"{t.get('n_loops', 0)} loops, {len(t['problems'])} problems" + (
            "; Loop polarity read from the base run with " + ", ".join(f"{k} = {v:g}" for k, v in t["polarity_run"].items())
            + f" ([loop_check]) only for the {len(t.get('polarity_from_loop_check', []))} loop(s) with a zero link at base;"
            " all others from the base run" if isinstance(t.get("polarity_run"), dict) else ""),
    }
    for k, t in T.items():
        res = "PASS" if t["pass"] else ("NOT ROBUST (reported)" if t.get("gating") is False else "FAIL")
        L.append(f"| {k} | {res} | {keynum.get(k, lambda t: '')(t)} |")
    L.append("")
    for k in ("T1_units", "T1b_mece", "T1c_parameter_ranges", "T3_extremes", "T4_dt_halving", "T6_conservation", "T8_loops"):
        p = T.get(k, {}).get("problems") or T.get(k, {}).get("failures")
        if p:
            L += [f"**{k} problems:**", ""] + [f"- {x}" for x in p[:40]] + [""]
    t4 = T.get("T4_dt_halving")
    if t4:
        L += ["## T4 integration error", "", f"dt = {t4['dt']}; compared on the saved grid.", "",
              "| Output | base: dt vs dt/2 | corner: dt vs dt/2 | Euler error ratio (dt vs dt/2, ref dt/4) |", "|---|---|---|---|"]
        for c in t4["base"]:
            L.append(f"| {c} | {fmt(t4['base'][c])} | {fmt(t4['corner'][c])} | {fmt(t4['euler_error_ratio_dt_vs_dt2'][c], 3)} |")
        L += ["", "Error ratio: |x(dt) - x(dt/4)| / |x(dt/2) - x(dt/4)|; first-order (Euler) convergence gives 3.", "",
              f"Corner parameters (time constants low, rates high): `{t4['corner_params']}`", ""]
    t6 = T.get("T6_conservation")
    if t6:
        L += ["## T6 conservation", "", "| Run set | Max relative drift |", "|---|---|"]
        L += [f"| {k} | {fmt(v)} |" for k, v in t6["max_rel_drift"].items()] + [""]
    t5 = T.get("T5_behavior")
    if t5 and "nrmse" in t5:
        L += ["## T5 behavior reproduction", "", f"Limit case `{t5['limit_case']}` vs `{t5['reference']}`, "
              f"comparing sum of {t5['compare']}: NRMSE = {fmt(t5['nrmse'])}.", ""]
        if t5["peak"]:
            p = t5["peak"]
            if "analytic" in p:
                L.append(f"Peak of `{p['var']}`: simulated t = {fmt(p['sim'])}, analytic t* = {fmt(p['analytic'])}, "
                         f"error {fmt(p['error'])} (tolerance {p['tolerance']}; rule: {PEAK_STEPS} x reference dt = {fmt(p['rule'])}).")
            else:
                L.append(f"Peak of `{p['var']}`: {p['error']}.")
        L += ["", "| Variable (base case) | Expected mode | Detected | Pass |", "|---|---|---|---|"]
        L += [f"| {x['var']} | {x['expected']} | {x['got']} | {x['pass']} |" for x in t5["modes"]] + [""]
    t3 = T.get("T3_extremes")
    if t3 and t3["expectations"]:
        L += ["## T3 extreme-condition expectations", "", "| Case | Check | Value | Pass |", "|---|---|---|---|"]
        L += [f"| {r['case']} | {r['check']} | {fmt(r['value'])} | {r['pass']} |" for r in t3["expectations"]] + [""]
    if not R.get("all_pass"):
        L += ["## Results", "", "**WITHHELD**: at least one gating test failed. Fix the model or spec and rerun.", ""]
        stale = [f for f in RELEASE_FILES if os.path.exists(os.path.join(d, f))]
        for f in stale:  # results released by an earlier passing run no longer describe a valid model
            os.remove(os.path.join(d, f))
        if stale:
            L += ["Removed previously released results: " + ", ".join(f"`{f}`" for f in stale) + ".", ""]
        open(os.path.join(d, "validation_report.md"), "w").write("\n".join(L))
        R["output_files"] = {}
        json.dump(R, open(os.path.join(d, "validation_results.json"), "w"), indent=1, default=str)
        return
    # results: only when everything passed
    t7, t8 = T["T7_monte_carlo"], T["T8_loops"]
    L += ["## T7 Monte Carlo", "", f"N = {t7['n']} Latin hypercube samples (seed {t7['seed']}) over: "
          + ", ".join(f"`{x}`" for x in t7["sampled_parameters"]) + ".", "",
          "| Metric | P5 | P25 | P50 | P75 | P95 |", "|---|---|---|---|---|---|"]
    for k, v in t7["metrics"].items():
        L.append(f"| {k} | " + " | ".join(fmt(v[p], 4) for p in ("P5", "P25", "P50", "P75", "P95")) + " |")
    L += ["", "Spearman rank correlation, parameter vs metric (|rho| > 0.3 in bold):", "",
          "| Parameter | " + " | ".join(t7["spearman"]) + " |", "|---|" + "---|" * len(t7["spearman"])]
    for nm in t7["sampled_parameters"]:
        cells = []
        for k in t7["spearman"]:
            r = t7["spearman"][k][nm]
            cells.append(f"**{r:+.2f}**" if abs(r) > 0.3 else f"{r:+.2f}")
        L.append(f"| {nm} | " + " | ".join(cells) + " |")
    L.append("")
    tb = T.get("T7b_policy_ranking")
    if tb:
        L += ["## T7b policy ranking (common random numbers, same samples per scenario)", "",
              f"Objective: `{tb['objective']}` ({'higher' if tb['maximize'] else 'lower'} is better). "
              f"Modal ranking: {' > '.join(tb['modal_ranking'])}; identical full ranking in "
              f"{fmt(tb['full_ranking_stability'] * 100, 3)}% of samples; best policy `{tb['best_policy']}` in "
              f"{fmt(tb['best_policy_stability'] * 100, 3)}%.", "",
              "| Scenario | P5 | P50 | P95 | Gain vs base P5 | P50 | P95 |", "|---|---|---|---|---|---|---|"]
        for k, v in tb["scenarios"].items():
            L.append(f"| {k} | {fmt(v['P5'])} | {fmt(v['P50'])} | {fmt(v['P95'])} | {fmt(v['gain_vs_base_P5'])} | "
                     f"{fmt(v['gain_vs_base_P50'])} | {fmt(v['gain_vs_base_P95'])} |")
        L.append("")
    L += ["## T8 loops and dominance (base case, LTM relative loop scores)", "",
          "| Loop | Declared name | Polarity | Variables | Mean abs rel. score | Max abs rel. score |", "|---|---|---|---|---|---|"]
    if isinstance(t8.get("polarity_run"), dict):
        L.insert(len(L) - 2, "Loop polarity read from the base run with " + ", ".join(f"{k} = {v:g}" for k, v in t8["polarity_run"].items())
                 + " ([loop_check]) only for loops with a zero link at base: "
                 + (", ".join(t8.get("polarity_from_loop_check", [])) or "none")
                 + ". All other polarities, and all scores and dominance below, are from the true base run.\n")
    for x in t8["loops"]:
        L.append(f"| {x['id']} | {x['name']} | {x['polarity']} | {' -> '.join(x['variables'])} | "
                 f"{fmt(x['mean_abs_relative_score'], 3)} | {fmt(x['max_abs_relative_score'], 3)} |")
    L += ["", f"Dominance periods (periods shorter than {spec.get('dominance_min_period', 1.0)} time units folded into the previous one):", "",
          "| From | To | Dominant loop | Mean relative score |", "|---|---|---|---|"]
    names = {x["id"]: x["name"] for x in t8["loops"]}
    for p in t8["dominance"]:
        L.append(f"| {fmt(p['start'])} | {fmt(p['end'])} | {p['loop']} {names.get(p['loop']) or ''} | {fmt(p['mean_relative_score'], 3)} |")
    L.append("")
    open(os.path.join(d, "validation_report.md"), "w").write("\n".join(L))
    import csv
    with open(os.path.join(d, "mc_bands.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["time"] + [f"{c}|{p}" for c in results["bands"] for p in ("P5", "P25", "P50", "P75", "P95")])
        for i, t in enumerate(results["band_time"]):
            w.writerow([t] + [f"{results['bands'][c][p][i]:.6g}" for c in results["bands"] for p in ("P5", "P25", "P50", "P75", "P95")])
    if tb:
        with open(os.path.join(d, "policy_results.csv"), "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["scenario", "P5", "P50", "P95", "gain_P5", "gain_P50", "gain_P95"])
            for k, v in tb["scenarios"].items():
                w.writerow([k] + [f"{v[x]:.6g}" for x in ("P5", "P50", "P95", "gain_vs_base_P5", "gain_vs_base_P50", "gain_vs_base_P95")])
    if la:
        keep = {k: la[k] for k in ("loops", "dominance")}
        step = max(1, len(la["time"]) // 480)
        keep["time"] = la["time"][::step]
        keep["relative_scores"] = {k: [round(x, 5) if x == x else None for x in v[::step]] for k, v in la["relative_scores"].items()}
        json.dump(keep, open(os.path.join(d, "loop_dominance.json"), "w"), indent=1)
    # a release holds only what this run produced: drop optional files left by an earlier run
    produced = {"mc_bands.csv"} | ({"policy_results.csv"} if tb else set()) | ({"loop_dominance.json"} if la else set())
    for f in set(RELEASE_FILES) - produced:
        if os.path.exists(os.path.join(d, f)):
            os.remove(os.path.join(d, f))
    # record-only: the sha256 of each result file as this run wrote it, so later tools can tell if one was edited
    R["output_files"] = {f: hashlib.sha256(open(os.path.join(d, f), "rb").read()).hexdigest() for f in sorted(produced)}
    json.dump(R, open(os.path.join(d, "validation_results.json"), "w"), indent=1, default=str)


def main(argv):
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--n", type=int, help="Monte Carlo sample size (>= 1000)")
    ap.add_argument("--workers", type=int)
    a = ap.parse_args(argv)
    try:
        spec, R, results = run_all(a.spec, a.n, a.workers)
    except Exception as e:  # noqa: BLE001 - any crash still yields a written, failed report
        # the spec itself may be unreadable: report from its directory without parsing it again
        d = os.path.dirname(os.path.abspath(a.spec))
        spec = {"_dir": d}
        R = {"model": os.path.basename(d), "tests": {}, "all_pass": False,
             "fatal": f"{type(e).__name__}: {e}"[:500]}
        results = None
    try:
        write_outputs(spec, R, results)
    except Exception as e:  # noqa: BLE001 - never leave an earlier run's results file behind: record a failure, re-raise
        R = {k: v for k, v in R.items() if k != "_loop_analysis"}
        R.update(all_pass=False, output_files={}, fatal=f"write_outputs failed: {type(e).__name__}: {e}"[:500])
        json.dump(R, open(os.path.join(spec["_dir"], "validation_results.json"), "w"), indent=1, default=str)
        raise
    for k, t in R["tests"].items():
        tag = "PASS" if t["pass"] else ("NOT ROBUST" if t.get("gating") is False else "FAIL")
        print(f"{tag}  {k}" + ("  (reported, not gating)" if t.get("gating") is False else ""))
    print("ALL PASS" if R.get("all_pass") else "VALIDATION FAILED: results withheld")
    return 0 if R.get("all_pass") else 1


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--worker":
        worker(sys.argv[2])
    else:
        sys.exit(main(sys.argv[1:]))
