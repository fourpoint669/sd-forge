"""Screen for a PySD-generated model file: is it plain PySD output, or did a model text field escape its string?

PySD writes each Vensim comment into a triple-quoted docstring without escaping it, so a comment that closes the
docstring adds code to the translation, and every run imports that file. engine/validate.py translate() calls
problems() on each fresh translation and refuses a file that has any. Standard library only.
"""
import ast
import os

# Names and attributes a PySD translation never uses. Their presence in a generated file means a model text field
# escaped its docstring (PySD writes Vensim comments into triple-quoted docstrings without escaping them).
_FORBIDDEN_NAMES = frozenset({"__import__", "eval", "exec", "compile", "open", "input", "os", "sys", "subprocess",
                              "builtins", "globals", "locals", "vars", "getattr", "setattr", "delattr", "breakpoint",
                              "importlib", "shutil", "socket", "ctypes", "pickle", "marshal"})
_FORBIDDEN_STATEMENTS = (ast.Try, ast.With, ast.AsyncWith, ast.Delete, ast.Global, ast.Nonlocal, ast.Raise,
                         ast.Assert, ast.ClassDef, ast.AsyncFunctionDef, ast.While)
_ALLOWED_IMPORTS = frozenset({"numpy", "xarray", "pathlib", "pysd"})


def problems(py):
    """Reasons a PySD-generated model file is not plain PySD output (empty list = looks like a translation).

    A translation has docstrings, imports of numpy/xarray/pathlib/pysd, assignments, `return` statements and
    simple loops. This is a screen against a crafted comment or name that closes a docstring and adds code; it does
    not make running an untrusted model safe (see the manual: use only models you trust)."""
    try:
        tree = ast.parse(open(py, encoding="utf-8").read())
    except (OSError, SyntaxError, ValueError) as e:
        return [f"{os.path.basename(py)} cannot be parsed ({type(e).__name__})"]
    out = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, _FORBIDDEN_STATEMENTS):
            out.append(f"line {line}: {type(node).__name__} statement")
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            mods = [node.module or ""] if isinstance(node, ast.ImportFrom) else [a.name for a in node.names]
            if any(m.split(".")[0] not in _ALLOWED_IMPORTS for m in mods):
                out.append(f"line {line}: import of {', '.join(mods)}")
        elif isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            out.append(f"line {line}: the name {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr.startswith("__") and node.attr.endswith("__"):
            out.append(f"line {line}: the attribute {node.attr}")
    containers = [tree] + [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.For, ast.If))]
    for c in containers:
        for i, stmt in enumerate(c.body + (getattr(c, "orelse", []) or [])):
            if isinstance(stmt, ast.Expr):
                is_doc = (i == 0 and isinstance(c, (ast.Module, ast.FunctionDef)) and isinstance(stmt.value, ast.Constant)
                          and isinstance(stmt.value.value, str))
                if not is_doc:
                    out.append(f"line {stmt.lineno}: an expression statement ({type(stmt.value).__name__})")
    return out
