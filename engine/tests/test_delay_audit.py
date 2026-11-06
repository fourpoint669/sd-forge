"""engine/delay_audit.py: every delay structure in a validated model, read from the PySD code (report only)."""
import os

import pytest

import delay_audit as da

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASS = os.path.join(ROOT, "projects", "bass-b2b-adoption")
SAAS = os.path.join(ROOT, "projects", "saas-churn-vs-winrate")


@pytest.fixture(scope="module")
def bass():
    return {r["stock"]: r for r in da.audit(BASS)["stocks"]}


@pytest.fixture(scope="module")
def saas():
    return {r["stock"]: r for r in da.audit(SAAS)["stocks"]}


def test_every_stock_is_listed(bass, saas):
    assert len(bass) == 4 and len(saas) == 11


def test_bass_pipeline_is_first_order_material_drain(bass):
    r = bass["Firms in Evaluation"]
    assert (r["form"], r["delay_type"], r["order"]) == ("drain", "material", 1)
    assert r["tau_var"] == "sales cycle time" and r["tau_base"] == 6 and r["tau_range"] == [3, 9]
    assert sorted(r["outflows"]) == ["deals lost", "deals won"]
    assert r["first_order_candidate"] is True


def test_bass_cool_off_and_churn(bass):
    assert (bass["Cooling Off Firms"]["form"], bass["Cooling Off Firms"]["tau_var"]) == ("drain", "cool off time")
    c = bass["Customers"]
    assert (c["form"], c["delay_type"], c["state_dependent"]) == ("rate", "material", False)
    assert c["tau_base"] == pytest.approx(12 / 0.08)            # 1 / churn rate monthly, months


def test_bass_adoption_exit_is_state_dependent(bass):
    r = bass["Potential Customers"]
    assert r["form"] == "rate" and r["state_dependent"] is True


def test_saas_capacity_capped_pipeline(saas):
    r = saas["Firms in Evaluation"]
    assert r["form"] == "drain_capped" and r["tau_var"] == "sales cycle time"
    assert r["cap_var"] == "sales capacity"


def test_saas_information_delays(saas):
    for stock, tau in (("CS Capacity", "CS ramp up time"), ("Win Rate Capability", "enablement ramp up time")):
        r = saas[stock]
        assert (r["form"], r["delay_type"], r["tau_var"], r["order"]) == ("goal_seeking", "information", tau, 1)
    r = saas["Recently Churned Firms"]
    assert (r["form"], r["delay_type"], r["tau_var"]) == ("drain", "information", "detractor memory time")


def test_saas_non_delays(saas):
    assert saas["ARR"]["form"] == "coflow" and saas["ARR"]["coflow_of"] == "Customers"
    assert saas["Cumulative Revenue"]["form"] == "accumulator"
    assert saas["Cumulative Programme Spend"]["form"] == "accumulator"
    assert saas["Firms Yet To Enter"]["form"] == "source"
    for s in ("ARR", "Cumulative Revenue", "Cumulative Programme Spend", "Firms Yet To Enter"):
        assert saas[s]["delay_type"] == "none" and saas[s]["first_order_candidate"] is False


def test_saas_churn_rate_varies_over_base_run(saas):
    r = saas["Customers"]
    assert r["form"] == "rate" and r["state_dependent"] is True
    lo, hi = r["tau_run"]
    assert 0 < lo < hi                                          # programme changes the residence time


def test_no_delay_or_smooth_functions():
    for d in (BASS, SAAS):
        assert da.audit(d)["functions"] == []


def test_markdown_keeps_hand_written_judgment(tmp_path):
    p = tmp_path / "delay_audit.md"
    p.write_text("old generated part\n" + da.MARKER + "\nmy judgment\n")
    rep = da.audit(BASS)
    text = da.write_markdown(rep, str(p))
    assert text.endswith(da.MARKER + "\nmy judgment\n")
    assert "old generated part" not in text


# The shapes PySD writes around a rate. Before these were read, a stock whose outflow was any of them got no pipe in the
# diagram and was reported as having no flows at all (projects/car-dealership-profit: six stocks).
SHAPES = [
    ("inflow() - outflow()", {(1, "inflow"), (-1, "outflow")}),
    ("-outflow()", {(-1, "outflow")}),
    ("float(rate())", {(1, "rate")}),
    ("float(np.maximum(0, net_flow()))", {(1, "net_flow")}),
    ("np.minimum(cap_const(), rate())", {(1, "rate")}),
    ("rate() * per_unit_const()", {(1, "rate")}),
    ("per_unit_const() * rate()", {(1, "rate")}),
    ("rate() / per_unit_const()", {(1, "rate")}),
    ("deliveries() - new_sales() * per_unit_const()", {(1, "deliveries"), (-1, "new_sales")}),
]
UNRESOLVED = [
    ("rate() * other_rate()", "two rates in a product: which one is the flow is not decidable"),
    ("per_unit_const() / rate()", "a rate in the denominator is not that rate"),
    ("np.maximum(rate(), other_rate())", "two rates under a cap"),
    ("per_unit_const()", "a constant is never a flow"),
]


@pytest.mark.parametrize("expr, want", SHAPES)
def test_signed_terms_reads_the_shapes_pysd_writes_around_a_rate(expr, want):
    import ast
    node = ast.parse(expr, mode="eval").body
    assert set(da.signed_terms(node, 1, frozenset({"per_unit_const", "cap_const"}))) == want


@pytest.mark.parametrize("expr, why", UNRESOLVED)
def test_signed_terms_drops_a_term_it_cannot_resolve_to_one_rate(expr, why):
    import ast
    node = ast.parse(expr, mode="eval").body
    assert da.signed_terms(node, 1, frozenset({"per_unit_const", "cap_const"})) == [], why


def test_the_audit_and_the_diagram_read_flows_with_the_same_function():
    """Two copies of this logic drifted apart once; the diagram's pipes are tested against the audit, so they must not
    be computed by a different reader."""
    import explorer_structure as es
    assert es.delay_audit.signed_terms is da.signed_terms


# Direction is the whole point of a flow term: a negative number written into the rate reverses it. The unary branch
# already handles -rate(); these are the forms where the minus sits on a factor.
SIGNS = [
    ("outflow() * -1", -1), ("-1 * outflow()", -1), ("outflow() / -1", -1), ("outflow() * -2.5", -1),
    ("outflow() * 2", 1), ("outflow() * per_unit_const()", 1),
    ("-outflow() * per_unit_const()", -1),              # the minus is on the rate, counted once, not twice
    ("-(outflow() * per_unit_const())", -1),
    ("outflow() * -1 * -1", 1),                          # two negations cancel
    ("-outflow() / per_unit_const()", -1),
]


@pytest.mark.parametrize("expr, want", SIGNS)
def test_a_negative_factor_reverses_the_flow(expr, want):
    import ast
    got = da.signed_terms(ast.parse(expr, mode="eval").body, 1, frozenset({"per_unit_const"}))
    assert got == [(want, "outflow")], f"{expr} is an {'outflow' if want < 0 else 'inflow'}"


def test_never_a_flow_covers_everything_that_cannot_be_a_valve():
    """A constant, a time control and a stock are all levels or inputs, never rates. Reading one as a flow put a
    non-node into the diagram's pipes (INTEG(Time, 0) crashed the build) or drew a stock as a valve."""
    import ast
    comps = da.ld.parse_model(os.path.join(BASS, "model", "bass_b2b_adoption.py")).comps
    never = da.never_a_flow(comps)
    kinds = {c.ctype for p, c in comps.items() if p in never}
    assert kinds == {"Constant", "Control", "Stateful"}
    assert {"time", "saveper"} <= never and "cool_off_time" in never and "customers" in never
    assert "churn" not in never                                    # a rate is still a rate

    def terms(expr):
        return da.signed_terms(ast.parse(expr, mode="eval").body, 1, never)
    assert terms("time()") == []                                   # INTEG(Time, 0): no valve to draw
    # a capped drain: the stock and its time constant drop out, so the one rate left is the valve
    assert terms("-np.minimum(customers() / cool_off_time(), churn())") == [(-1, "churn")]
    assert terms("-np.minimum(customers() / cool_off_time(), 3)") == []         # reduces to a stock: a level, not a rate
    assert terms("foo.maximum(0, churn())") == []                  # only np.maximum is the clamp PySD writes
    assert terms("np.maximum(0, churn())") == [(1, "churn")]
