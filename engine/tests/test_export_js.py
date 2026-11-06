"""engine/export_js.py: PySD .py -> JavaScript Euler engine. Expression-level tests run without PySD or node."""
import ast
import json
import os
import random
import re
import shutil

import pytest

import export_js

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASS_PY = os.path.join(ROOT, "projects", "bass-b2b-adoption", "model", "bass_b2b_adoption.py")
SAAS_PY = os.path.join(ROOT, "projects", "saas-churn-vs-winrate", "model", "saas_churn_vs_winrate.py")


def js(src, names=("a", "b", "c"), stocks=()):
    return export_js.expr_js(ast.parse(src, mode="eval").body, set(names), set(stocks))


def test_binary_ops_fully_parenthesized_keeps_python_order():
    assert js("a() - b() - c()") == "((v_a - v_b) - v_c)"
    assert js("a() / (b() * 2)") == "(v_a / (v_b * 2))"


def test_power_uses_math_pow():
    assert js("a() ** 2") == "Math.pow(v_a, 2)"


def test_float_literal_round_trips():
    assert js("0.08333333333333333 * a()") == "(0.08333333333333333 * v_a)"


def test_stock_reference_uses_state_variable():
    assert js("a() / b()", stocks={"a"}) == "(s_a / v_b)"


def test_time_and_control_functions():
    assert js("time() * time_step()") == "(t * DT)"


def test_if_then_else_lambda_with_comparison():
    assert js("if_then_else(time() < a(), lambda: 1, lambda: b())") == "((t < v_a) ? 1 : v_b)"


def test_if_then_else_numeric_condition_uses_python_truthiness():
    # bool(nan) is True in Python; NaN is falsy in JS, so a bare number is compared with 0
    assert js("if_then_else(a(), lambda: 1, lambda: 0)") == "((v_a !== 0) ? 1 : 0)"


def test_np_maximum_minimum_exp_and_float_wrapper():
    assert js("float(np.maximum(0, a()))") == "Math.max(0, v_a)"
    assert js("float(np.minimum(a(), b()))") == "Math.min(v_a, v_b)"
    assert js("1 - float(np.exp(-a() / b()))") == "(1 - Math.exp(((-v_a) / v_b)))"


def test_chained_comparison_and_boolop():
    assert js("a() < b() < c()") == "((v_a < v_b) && (v_b < v_c))"
    assert js("(a() > 0) and (b() == 1)") == "((v_a > 0) && (v_b === 1))"


@pytest.mark.parametrize("src", [
    "np.log10(a())",            # not allowlisted
    "a(1)",                     # component called with an argument
    "unknown()",                # not a component
    "x",                        # bare name
    "a().real",                 # attribute access
    "[a()]",                    # container
    "a() or b()",               # boolean of non-booleans returns an operand in Python
    "np.maximum(a(), b=1)",     # keyword argument
])
def test_unsupported_construct_raises(src):
    with pytest.raises(export_js.Unsupported):
        js(src)


def test_load_ir_bass_structure():
    ir = export_js.load_ir(BASS_PY)
    assert ir["control"] == {"initial_time": 0, "final_time": 180, "time_step": 0.25, "saveper": 1}
    assert sorted(s["name"] for s in ir["stocks"]) == ["Cooling Off Firms", "Customers", "Firms in Evaluation",
                                                     "Potential Customers"]
    assert "win rate" in ir["parameters"]
    assert "Customers" not in ir["parameters"]
    # every non-stock, non-control component is evaluated exactly once per step
    assert len(ir["aux_order"]) == len(set(ir["aux_order"]))


def test_unsupported_stateful_raises(tmp_path):
    text = open(BASS_PY).read().replace("Integ(", "Smooth(", 1)
    p = tmp_path / "m.py"
    p.write_text(text)
    with pytest.raises(export_js.Unsupported):
        export_js.load_ir(str(p))


def test_emit_is_deterministic():
    a = export_js.emit_js(export_js.load_ir(SAAS_PY))
    b = export_js.emit_js(export_js.load_ir(SAAS_PY))
    assert a == b


def _shuffle_dependency_dicts(text, seed):
    """Reorder the keys of every depends_on / other_deps dict, as PySD does from run to run."""
    rnd = random.Random(seed)
    tree = ast.parse(text)

    class Shuffle(ast.NodeTransformer):
        def visit_Dict(self, node):
            self.generic_visit(node)
            pairs = list(zip(node.keys, node.values))
            rnd.shuffle(pairs)
            node.keys, node.values = [k for k, _ in pairs], [v for _, v in pairs]
            return node

    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef):
            for dec in n.decorator_list:
                if isinstance(dec, ast.Call):
                    for kw in dec.keywords:
                        if kw.arg in ("depends_on", "other_deps"):
                            Shuffle().visit(kw.value)
    return ast.unparse(tree)


def test_dependency_dict_order_does_not_change_output(tmp_path):
    base = export_js.emit_js(export_js.load_ir(SAAS_PY))
    for seed in (1, 2, 3):
        (tmp_path / str(seed)).mkdir()
        p = tmp_path / str(seed) / os.path.basename(SAAS_PY)
        p.write_text(_shuffle_dependency_dicts(open(SAAS_PY).read(), seed))
        out = export_js.emit_js(export_js.load_ir(str(p)))
        # the header names the source hash; everything else must be identical
        strip = lambda s: re.sub(r"sha256 [0-9a-f]{64}", "", s)  # noqa: E731
        assert strip(out) == strip(base)


def test_emitted_js_contains_no_external_reference():
    out = export_js.emit_js(export_js.load_ir(SAAS_PY))
    assert not re.search(r"https?://|import\s|require\(|fetch\(", out)


def test_eqs_reference_values_by_name_map():
    assert export_js.expr_js(ast.parse("a() * time()", mode="eval").body, {"a"}, set(), ref=lambda p: "V." + p) == "(V.a * V.time)"


def test_emit_eqs_lists_every_scorable_equation_with_its_inputs():
    ir = export_js.load_ir(BASS_PY)
    text = export_js.emit_eqs(BASS_PY)
    assert text.startswith("// sd-explorer equations") and "var SDEqs" in text
    assert not re.search(r"https?://|require\(|fetch\(", text)
    import json as _j
    meta = _j.loads(re.search(r"var SDEQ_META = (\{.*?\});", text).group(1))
    # every stock (scored on its net flow) and every non-constant auxiliary/flow has an equation and its inputs
    assert set(meta) == {py for py, c in ir["names"].items() if py not in ir["param_py"].values()}
    assert meta["customers"] == ["churn", "deals_won"]


def test_emit_eqs_matches_pysd_values(tmp_path):
    import json as _j, subprocess, shutil
    import validate
    spec = validate.load_spec(os.path.join(ROOT, "projects", "saas-churn-vs-winrate", "validation.toml"))
    df = validate.run_batch(spec["model"]["py_path"], [{"params": {}, "saveper_dt": True}])[0]
    ir = export_js.load_ir(SAAS_PY)
    k = 200
    V = {py: float(df[name].iloc[k]) for py, name in ir["names"].items() if name in df.columns}
    V["time"] = float(df.index[k])
    js = export_js.emit_eqs(SAAS_PY) + "\nprocess.stdout.write(JSON.stringify(Object.fromEntries(Object.keys(SDEqs).map(" \
        "(k) => [k, SDEqs[k](V)]))));"
    p = subprocess.run([shutil.which("node"), "-e", "const V = " + _j.dumps(V) + ";\n" + js], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    got = _j.loads(p.stdout)
    stock_names = {s["py"] for s in ir["stocks"]}
    for py, val in got.items():
        if py in stock_names:
            continue    # a stock's equation is its net flow, checked by the LTM gate
        want = V[py]
        assert abs(val - want) <= 1e-12 * max(abs(want), 1.0), py


CONTROLS_SRC = ('_control_vars = {"initial_time": lambda: -10, "final_time": lambda: 100,\n'
                '                 "time_step": lambda: 0.25, "saveper": lambda: time_step()}\n')


def test_control_vars_accept_the_forms_pysd_writes():
    """Vensim's default SAVEPER = TIME STEP and a negative INITIAL TIME are what PySD emits; validate.model_controls
    already resolves both, and the explorer build used to refuse them."""
    assert export_js._control_vars(ast.parse(CONTROLS_SRC)) == {
        "initial_time": -10, "final_time": 100, "time_step": 0.25, "saveper": 0.25}


def test_a_plain_control_number_keeps_the_type_it_was_written_with():
    src = '_control_vars = {"initial_time": lambda: 0, "final_time": lambda: 180, "time_step": lambda: 0.25, "saveper": lambda: 1}\n'
    out = export_js._control_vars(ast.parse(src))
    assert out == {"initial_time": 0, "final_time": 180, "time_step": 0.25, "saveper": 1}
    assert [type(v).__name__ for v in out.values()] == ["int", "int", "float", "int"]


@pytest.mark.parametrize("src, why", [
    ('_control_vars = {"saveper": lambda: time_step(), "time_step": lambda: saveper()}\n', "refers to itself"),
    ('_control_vars = {"saveper": lambda: open("x")}\n', "must be a number or another control variable"),
    ('_control_vars = {"saveper": 1}\n', "must be a lambda"),
])
def test_control_vars_still_refuse_what_is_not_a_number(src, why):
    with pytest.raises(export_js.Unsupported, match=why):
        export_js._control_vars(ast.parse(src))


@pytest.mark.parametrize("name", [
    "widgets</script><img src=x onerror=alert(1)>",
    "a <!--<script> b",                              # opens script-data-double-escaped in an inline script
    "x < y",
    "plain widgets",
])
def test_a_model_name_is_embedded_so_it_cannot_act_as_markup(name):
    """The generated engine is inlined in a <script> element. json.dumps does not escape '/', so a name like
    'x</script>' used to reach that element literally; the only thing left was the build's backstop refusal."""
    out = export_js.json_for_script({"names": {"x": name}}, sort_keys=True)
    assert "<" not in out
    assert json.loads(out) == {"names": {"x": name}}        # \u003c is an escape, not a change of value


def test_a_model_missing_a_control_variable_is_refused():
    """The generated engine reads all four unconditionally (var T0 = META.control.initial_time), so a missing one used
    to become `undefined` and every value in the page NaN."""
    src = '_control_vars = {"initial_time": lambda: 0, "final_time": lambda: 30, "time_step": lambda: 0.25}\n'
    with pytest.raises(export_js.Unsupported, match="saveper"):
        export_js._control_vars(ast.parse(src))
