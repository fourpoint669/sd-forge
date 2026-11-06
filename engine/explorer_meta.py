"""Provenance for every variable the sd-explorer page shows. Missing metadata raises MissingMetadata (build fails).

Sources, in order of authority:
  parameters   validation.toml (unit, validated range [low, high], domain) + assumptions_register.md row (source,
               confidence tag); definition = the model's own comment (PySD docstring) or its equation
  constants    assumptions_register.md row (named constants table) + model unit and comment
  stocks, flows, auxiliaries   model unit + model comment, equation rendered from the PySD code; tag "computed"
Definitions: the model's own comment (PySD docstring). A shown variable without one takes its plain-language definition
from projects/<m>/explorer_glossary.toml, which is explanatory text written for the page, NOT part of the validated
model (the .mdl and .py are never edited); the page labels it as such. Missing from both, a glossary entry for a
variable that already has a model comment, or a glossary name that is not a model variable fails the build.
A parameter is flagged illustrative when its register source says "illustrative" or summary.md's Model limits
section says "**<...name ending> is illustrative.**" (e.g. "Sales capacity is illustrative." -> initial sales capacity).
"""
import ast
import os
import re
import sys
import tomllib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import loop_detector as ld  # noqa: E402  (read-only dependency)
import run_mode  # noqa: E402

COMPUTED = "computed"
NAMED_CONSTANT = "named constant (not sampled)"


class MissingMetadata(Exception):
    """One or more shown variables lack required provenance."""


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _clean(s):
    return re.sub(r"[*`]", "", s).strip()


def _split_names(cell):
    name = re.sub(r"\s*\([^)]*\)\s*$", "", _clean(cell))
    parts = [p.strip() for chunk in name.split(",") for p in chunk.split(" / ") if p.strip()]
    if not parts:
        return []
    first = parts[0].split()
    out = [parts[0]]
    for p in parts[1:]:
        w = p.split()
        out.append(" ".join(first[:-len(w)] + w) if len(w) < len(first) else p)
    return out


def parse_register(text):
    """{lower-case name: {name, base, range, unit, source, confidence}} from every register table with a
    Parameter or Constant column. Rows naming several variables ('a, b', 'x phase 1 / phase 2') are split."""
    rows, lines, i = {}, text.splitlines(), 0
    while i < len(lines) - 1:
        if lines[i].lstrip().startswith("|") and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1]):
            head = [h.lower() for h in _cells(lines[i])]
            col = {}
            for j, h in enumerate(head):
                key = ("name" if h in ("parameter", "constant") else "base" if h in ("base", "value") else
                       "range" if h.startswith("range") else "unit" if h == "unit" else
                       "source" if h in ("source", "reason") else "confidence" if h == "confidence" else None)
                if key and key not in col:
                    col[key] = j
            i += 2
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                if "name" in col:
                    c = _cells(lines[i])
                    get = lambda k: c[col[k]] if k in col and col[k] < len(c) else None  # noqa: E731
                    names = _split_names(get("name") or "")
                    bases = [b.strip() for b in (get("base") or "").split(" / ")]
                    for n, name in enumerate(names):
                        rows[name.lower()] = {
                            "name": name,
                            "base": bases[n] if len(bases) == len(names) else get("base"),
                            "range": get("range"), "unit": get("unit"), "source": get("source"),
                            "confidence": _clean(get("confidence")) if get("confidence") else None}
                i += 1
        else:
            i += 1
    return rows


def model_limits(summary_text):
    """The summary's 'Model limits' section, verbatim (heading included, trailing blank lines removed)."""
    lines = summary_text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        m = re.match(r"^(#+)\s*Model limits", line, re.I)
        if m:
            level = len(m.group(1))
            out = [line]
            for nxt in lines[i + 1:]:
                h = re.match(r"^(#+)\s", nxt)
                if h and len(h.group(1)) <= level:
                    break
                out.append(nxt)
            return "".join(out).rstrip()
    raise MissingMetadata("summary.md has no 'Model limits' section")


def illustrative(name, row, limits_text):
    if row and row.get("source") and "illustrative" in row["source"].lower():
        return True
    for phrase in re.findall(r"\*\*(?:The\s+)?([^*]+?) is illustrative\.\*\*", limits_text, re.I):
        if name.lower().endswith(phrase.lower().strip()):
            return True
    return False


PREC = {ast.Add: 1, ast.Sub: 1, ast.Mult: 2, ast.Div: 2, ast.Pow: 4}
OPS = {ast.Add: " + ", ast.Sub: " − ", ast.Mult: " × ", ast.Div: " / ", ast.Pow: "^"}
CMP = {ast.Lt: " < ", ast.LtE: " ≤ ", ast.Gt: " > ", ast.GtE: " ≥ ", ast.Eq: " = ", ast.NotEq: " ≠ "}
CTRL = {"time": "Time", "time_step": "TIME STEP", "final_time": "FINAL TIME", "initial_time": "INITIAL TIME",
        "saveper": "SAVEPER"}
FN = {"maximum": "max", "minimum": "min"}


def equation_text(node, names):
    """Readable infix text of a PySD expression with real variable names (minimal parentheses)."""
    def go(n, parent=0, right=False):
        if isinstance(n, ast.Constant):
            v = n.value
            if isinstance(v, float):                   # %g keeps 6 digits: 10568557.06 was shown as 1.05686e+07, and for
                if v.is_integer() and abs(v) < 1e16:   # a constant this text is the only value the page shows
                    return str(int(v))
                return repr(v)
            return str(v)
        if isinstance(n, ast.BinOp):
            p = PREC[type(n.op)]
            s = go(n.left, p) + OPS[type(n.op)] + go(n.right, p, True)
            need = p < parent or (p == parent and right)
            return f"({s})" if need else s
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub):
            s = "−" + go(n.operand, 3)
            return f"({s})" if parent > 3 else s
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Not):
            return "NOT " + go(n.operand, 3)
        if isinstance(n, ast.Compare):
            s, left = [], n.left
            for op, r in zip(n.ops, n.comparators):
                s.append(go(left, 1) + CMP[type(op)] + go(r, 1))
                left = r
            return " AND ".join(s)
        if isinstance(n, ast.BoolOp):
            return (" AND " if isinstance(n.op, ast.And) else " OR ").join(go(v, 1) for v in n.values)
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name):
                if f.id in names and not n.args:
                    return names[f.id]
                if f.id in CTRL:
                    return CTRL[f.id]
                if f.id == "float":
                    return go(n.args[0], parent, right)
                if f.id == "if_then_else":
                    a, b = n.args[1], n.args[2]
                    a, b = getattr(a, "body", a), getattr(b, "body", b)
                    return f"IF {go(n.args[0])} THEN {go(a)} ELSE {go(b)}"
            if isinstance(f, ast.Attribute):
                return FN.get(f.attr, f.attr) + "(" + ", ".join(go(a) for a in n.args) + ")"
        return ast.unparse(n)
    return go(node)


def _docstrings(py_path):
    out = {}
    for node in ast.parse(open(py_path).read()).body:
        if isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call):
                    kw = {k.arg: k.value for k in dec.keywords}
                    if "name" in kw:
                        out[ast.literal_eval(kw["name"])] = (ast.get_docstring(node) or "").strip()
    return out


GLOSSARY = "explorer_glossary.toml"


def load_glossary(project_dir):
    """{variable name: plain-language definition} from explorer_glossary.toml ({} if the file is absent)."""
    path = os.path.join(project_dir, GLOSSARY)
    if not os.path.exists(path):
        return {}
    return {k: v["definition"].strip() for k, v in tomllib.load(open(path, "rb")).get("variables", {}).items()}


def build_metadata(spec, ir, project_dir):
    """{'variables': {real name: {...}}, 'model_limits': str}. Raises MissingMetadata listing every gap."""
    reg = parse_register(open(os.path.join(project_dir, "assumptions_register.md")).read())
    limits = model_limits(open(os.path.join(project_dir, "summary.md")).read())
    mode = run_mode.read_mode(project_dir, run_mode.STAMPED_RECORDS)[0]   # stamped files only; checkpoint / express projects say what no person reviewed
    model = ld.parse_model(spec["model"]["py_path"])
    docs = _docstrings(spec["model"]["py_path"])
    names = ir["names"]
    stock_set = {s["py"] for s in ir["stocks"]}
    flows = set()
    for py in stock_set:
        flows |= ld._calls(model.comps[py].flow, set(names))
    params = spec["parameters"]
    glossary = load_glossary(project_dir)
    out, problems = {}, []
    for g in sorted(set(glossary) - set(names.values())):
        problems.append(f"glossary entry '{g}' is not a model variable")
    for py in sorted(names, key=lambda p: names[p]):
        c, name = model.comps[py], names[py]
        row = reg.get(name.lower())
        m = {"name": name, "py": py, "unit": c.units, "definition": docs.get(name), "definition_source": "model",
             "illustrative": False, "range": None, "domain": None}
        if docs.get(name):
            if name in glossary:
                problems.append(f"glossary entry for '{name}' duplicates the model's own definition")
        elif glossary.get(name):
            m["definition"], m["definition_source"] = glossary[name], "glossary"
        else:
            problems.append(f"'{name}' has no model definition and no entry in {GLOSSARY}")
        if py in stock_set:
            m.update(kind="stock", source="model equation", confidence=COMPUTED,
                     equation=f"{name} = ∫ ({equation_text(c.flow, names)}) dt, initial value: "
                              f"{equation_text(c.init, names)}")
        elif name in params:
            v = params[name]
            m.update(kind="parameter", unit=v.get("unit") or c.units, range=[v["low"], v["high"]],
                     domain=v.get("domain"), base=v["base"], fixed=v.get("distribution") == "fixed",
                     equation=f"{name} = {equation_text(c.expr, names)}",
                     source=row and row["source"], confidence=row and row["confidence"])
            if not row:
                problems.append(f"parameter '{name}' has no row in assumptions_register.md")
            m["illustrative"] = illustrative(name, row, limits)
        elif c.ctype == "Constant":
            m.update(kind="constant", equation=f"{name} = {equation_text(c.expr, names)}",
                     source=row and row["source"], confidence=(row and row["confidence"]) or NAMED_CONSTANT)
            if not row:
                problems.append(f"constant '{name}' has no row in assumptions_register.md")
        else:
            m.update(kind="flow" if py in flows else "auxiliary", source="model equation", confidence=COMPUTED,
                     equation=f"{name} = {equation_text(c.expr, names)}")
        for key in ("unit", "definition", "source", "confidence"):
            if not m.get(key) and not any(f"'{name}'" in p for p in problems):
                problems.append(f"'{name}' has no {key}")
        out[name] = m
    if problems:
        raise MissingMetadata("; ".join(problems))
    return {"variables": out, "model_limits": run_mode.limits_with_label(limits, mode), "run_mode": mode}
