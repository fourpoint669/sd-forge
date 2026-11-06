"""engine/explorer_structure.py: the diagram data behind the Structure tab (nodes, pipes, links, delays, loops, layout)."""
import json
import os

import pytest

import explorer_structure as es
import validate

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROJECTS = {"bass-b2b-adoption": 11, "saas-churn-vs-winrate": 22}


@pytest.fixture(scope="module", params=sorted(PROJECTS))
def built(request):
    d = os.path.join(ROOT, "projects", request.param)
    spec = validate.load_spec(os.path.join(d, "validation.toml"))
    return request.param, d, spec, es.build_structure(d)


def test_loops_equal_declared_loops(built):
    project, _, spec, st = built
    assert len(st["loops"]) == PROJECTS[project]
    declared = {l["name"]: (l["polarity"], frozenset(l["variables"])) for l in spec["loops"]}
    got = {l["name"]: (l["polarity"], frozenset(st["nodes"][n]["name"] for n in l["nodes"])) for l in st["loops"]}
    assert got == declared


def test_every_loop_edge_is_a_drawn_link_and_signs_give_polarity(built):
    _, _, _, st = built
    links = {(k["from"], k["to"]): k for k in st["links"]}
    for lp in st["loops"]:
        signs = []
        for a, b in lp["edges"]:
            assert (a, b) in links, (lp["name"], a, b)
            signs.append(links[(a, b)]["sign"])
        assert all(s in "+-" for s in signs), (lp["name"], signs)
        assert ("R" if signs.count("-") % 2 == 0 else "B") == lp["polarity"]


def test_every_node_exists_in_the_model_and_every_stock_and_flow_is_drawn(built):
    _, d, spec, st = built
    import export_js
    names = set(export_js.load_ir(spec["model"]["py_path"])["names"].values())
    assert {n["name"] for n in st["nodes"].values()} == names
    audit = json.load(open(os.path.join(d, "delay_audit.json")))
    stocks = {r["stock"] for r in audit["stocks"]}
    assert {n["name"] for n in st["nodes"].values() if n["kind"] == "stock"} == stocks
    flows = {f for r in audit["stocks"] for f in r["inflows"] + r["outflows"]}
    assert {st["nodes"][p["flow"]]["name"] for p in st["pipes"]} == flows


def test_pipes_match_stock_equations(built):
    _, d, _, st = built
    audit = {r["stock"]: r for r in json.load(open(os.path.join(d, "delay_audit.json")))["stocks"]}
    nm = lambda k: st["nodes"][k]["name"] if k else None  # noqa: E731
    for p in st["pipes"]:
        f = nm(p["flow"])
        for src in p["from"]:
            assert f in audit[nm(src)]["outflows"]
        for t in p["to"]:
            assert f in audit[nm(t)]["inflows"]


def test_delay_marks_equal_the_audit(built):
    _, d, _, st = built
    audit = {r["stock"]: r for r in json.load(open(os.path.join(d, "delay_audit.json")))["stocks"]
             if r["first_order_candidate"]}
    marks = [k for k in st["links"] if k.get("delay")]
    assert {k["delay"]["stock"] for k in marks} == set(audit)
    for k in marks:
        a = audit[k["delay"]["stock"]]
        assert k["delay"]["order"] == a["order"] and k["delay"]["tau"] == a["tau"]
        assert k["delay"]["tau_base"] == a["tau_base"] and k["delay"]["type"] == a["delay_type"]
        assert st["nodes"][k["from"]]["name"] == a["stock"]


def test_exogenous_inputs_and_zoom_levels(built):
    _, _, spec, st = built
    for n in st["nodes"].values():
        assert n["exogenous"] == (n["kind"] in ("parameter", "constant"))
        assert n["level"] == (0 if n["kind"] in ("stock", "flow") else 1)


def test_layout_inside_sector_regions_without_overlap(built):
    _, _, spec, st = built
    regions = {r["sector"]: r for r in st["sectors"]}
    order = [r["sector"] for r in st["sectors"]]
    assert set(order) >= set(spec["sectors"])
    with_stocks = {n["sector"] for n in st["nodes"].values() if n["kind"] == "stock"}
    k = len(with_stocks)
    assert set(order[:k]) == with_stocks                       # sectors holding stocks come first, in chain order
    rest = [s for s in spec["sectors"] if s not in with_stocks]
    assert [s for s in order[k:] if s in rest] == rest
    by_sector = {}
    for n in st["nodes"].values():
        r = regions[n["sector"]]
        assert r["x"] <= n["x"] <= r["x"] + r["w"] and r["y"] <= n["y"] <= r["y"] + r["h"], n["name"]
        by_sector.setdefault(n["sector"], []).append((n["x"], n["y"]))
    for pts in by_sector.values():
        assert len(set(pts)) == len(pts)


def test_structure_is_deterministic(built):
    _, d, _, st = built
    assert json.dumps(es.build_structure(d), sort_keys=True) == json.dumps(st, sort_keys=True)


def test_every_link_has_a_sign_and_its_method(built):
    _, _, _, st = built
    loop_edges = {tuple(e) for lp in st["loops"] for e in lp["edges"]}
    for k in st["links"]:
        assert k["sign"] in ("+", "-", "+/-", "0"), (k["from"], k["to"], k["sign"])
        assert k["sign_method"] in ("ltm", "loop_check", "perturbation", "perturbation_optional_on", "inactive")
        assert (k["sign"] == "0") == (k["sign_method"] == "inactive")
        if (k["from"], k["to"]) in loop_edges:
            assert k["sign"] in "+-"
    assert any(k["sign_method"] == "perturbation" for k in st["links"])


def test_known_signs_bass():
    st = es.build_structure(os.path.join(ROOT, "projects", "bass-b2b-adoption"))
    sign = {(st["nodes"][k["from"]]["name"], st["nodes"][k["to"]]["name"]): k["sign"] for k in st["links"]}
    assert sign[("win rate", "deals won")] == "+"
    assert sign[("win rate", "deals lost")] == "-"
    assert sign[("sales cycle time", "deal closings")] == "-"
    assert sign[("churn", "Customers")] == "-"


def test_material_chain_reads_left_to_right_inside_each_sector(built):
    _, _, _, st = built
    n = st["nodes"]
    for p in st["pipes"]:
        for src in p["from"]:
            for t in p["to"]:
                a, b = n[src], n[t]
                if a["sector"] == b["sector"] and abs(a["y"] - b["y"]) < 1:
                    back = any(t in q["from"] and src in q["to"] for q in st["pipes"])
                    if not back:
                        assert a["x"] < b["x"], (a["name"], b["name"])


def test_chain_sector_order_bass():
    st = es.build_structure(os.path.join(ROOT, "projects", "bass-b2b-adoption"))
    assert [r["sector"] for r in st["sectors"]][:3] == ["market pool", "sales pipeline", "customer base"]


def test_regions_packed_to_a_screen_like_aspect(built):
    _, _, _, st = built
    w = max(r["x"] + r["w"] for r in st["sectors"]) - min(r["x"] for r in st["sectors"])
    h = max(r["y"] + r["h"] for r in st["sectors"]) - min(r["y"] for r in st["sectors"])
    assert 0.8 <= w / h <= 3.2, w / h


def test_valves_sit_with_one_of_their_stocks(built):
    _, _, _, st = built
    n = st["nodes"]
    for p in st["pipes"]:
        ends = {n[s]["sector"] for s in p["from"] + p["to"]}
        if ends:
            assert n[p["flow"]]["sector"] in ends, n[p["flow"]]["name"]
        assert n[p["flow"]]["declared_sector"]


def test_overview_layout_has_only_stocks_and_flows_and_is_compact(built):
    _, _, _, st = built
    n = st["nodes"]
    ov = {r["sector"]: r for r in st["overview"]}
    pts = []
    for v in n.values():
        if v["level"] == 0:
            r = ov[v["sector"]]
            assert r["x"] <= v["ox"] <= r["x"] + r["w"] and r["y"] <= v["oy"] <= r["y"] + r["h"], v["name"]
            pts.append((v["ox"], v["oy"]))
        else:
            assert "ox" not in v
    assert len(set(pts)) == len(pts)
    area = lambda rs: sum(r["w"] * r["h"] for r in rs)  # noqa: E731
    assert area(st["overview"]) < 0.75 * area(st["sectors"])


def test_overview_regions_keep_title_band_and_corridor_clear(built):
    _, _, _, st = built
    g = st["overview_geometry"]
    for v in st["nodes"].values():
        if v["level"] == 0:
            assert v["oly"] == g["row_y"]                     # a single, unwrapped pipe row
            assert v["oly"] - 32 >= g["title_band"] + g["corridor"]
    ov = {r["sector"]: r for r in st["overview"]}
    for v in st["nodes"].values():
        if v["level"] == 0:
            assert 0 < v["olx"] < ov[v["sector"]]["w"]


def test_local_coordinates_match_the_default_packing(built):
    _, _, _, st = built
    for key, (gx, gy, lx, ly) in (("sectors", ("x", "y", "lx", "ly")), ("overview", ("ox", "oy", "olx", "oly"))):
        pos = {r["sector"]: r for r in st[key]}
        for v in st["nodes"].values():
            if lx in v:
                r = pos[v["sector"]]
                assert abs(r["x"] + v[lx] - v[gx]) < 0.2 and abs(r["y"] + v[ly] - v[gy]) < 0.2


def test_overview_leaves_room_for_stock_names(built):
    _, _, _, st = built
    for r in st["overview"]:
        assert r["h"] >= st["overview_geometry"]["row_y"] + 30 + 2 * 46


def test_pooling_groups_and_capped_flows_from_validated_files(built):
    project, d, spec, st = built
    pool = st["pooling"]
    assert [g["name"] for g in pool["groups"]] == [g["name"] for g in spec["conservation"]]
    for g, c in zip(pool["groups"], spec["conservation"]):
        assert [st["nodes"][s]["name"] for s in g["stocks"]] == c["stocks"]
    audit = json.load(open(os.path.join(d, "delay_audit.json")))["stocks"]
    capped = [r for r in audit if r["form"] == "drain_capped"]
    assert [(c["stock_name"], c["cap_name"], c["tau_name"]) for c in pool["capped"]] == \
        [(r["stock"], r["cap_var"], r["tau_var"]) for r in capped]
    if project == "saas-churn-vs-winrate":
        assert pool["capped"][0]["outflow_names"] == ["deals lost", "deals won"]


def test_delay_list_equals_the_audit(built):
    _, d, _, st = built
    audit = [r for r in json.load(open(os.path.join(d, "delay_audit.json")))["stocks"] if r["first_order_candidate"]]
    assert [(x["stock"], x["order"], x["tau"], x["tau_base"]) for x in st["delays"]] == \
        [(r["stock"], r["order"], r["tau"], r["tau_base"]) for r in audit]


SHIPPED = ("bass-b2b-adoption", "saas-churn-vs-winrate", "car-dealership-profit")


def _page_structure(project):
    import json as _json
    import re as _re
    page = os.path.join(ROOT, "projects", project, "explorer.html")
    if not os.path.exists(page):
        pytest.skip(f"{project} ships no explorer.html")
    html = open(page, encoding="utf-8").read()
    blob = _re.search(r'<script id="sd-data" type="application/json">(.*?)</script>', html, _re.S).group(1)
    return _json.loads(blob)["structure"]


@pytest.mark.parametrize("project", SHIPPED)
def test_every_flow_the_audit_lists_is_drawn_in_the_shipped_page(project):
    """Six stocks of car-dealership-profit were drawn with no flow at all (New Inventory filled and never drained)
    because the diagram read fewer flow shapes than the audit. Every stock's inflows must match exactly, and no
    outflow may be missing from the diagram, and every stock a flow drains must name that stock as one of the pipe's
    sources (a flow draining two stocks - a coflow - used to keep only the first)."""
    st = _page_structure(project)
    audit = json.load(open(os.path.join(ROOT, "projects", project, "delay_audit.json")))
    name = lambda k: st["nodes"][k]["name"] if k else None  # noqa: E731
    drawn = {name(p["flow"]) for p in st["pipes"]}
    drains = {}
    for r in audit["stocks"]:
        for f in r["outflows"]:
            drains.setdefault(f, []).append(r["stock"])
    for r in audit["stocks"]:
        ins = {name(p["flow"]) for p in st["pipes"] if r["stock"] in [name(t) for t in p["to"]]}
        assert ins == set(r["inflows"]), (project, r["stock"], "inflows")
        for f in r["outflows"]:
            assert f in drawn, (project, r["stock"], f, "outflow is not drawn at all")
            pipe = [p for p in st["pipes"] if name(p["flow"]) == f][0]
            assert r["stock"] in [name(x) for x in pipe["from"]], (project, r["stock"], f, "outflow names another stock")


@pytest.mark.parametrize("project", SHIPPED)
def test_every_pipe_end_is_a_node_the_page_holds(project):
    """A rate that is not a diagram variable - a control, as in INTEG(Time, 0) - must never reach the pipes: the page
    would look it up in nodes and the build would die on a KeyError."""
    st = _page_structure(project)
    for p in st["pipes"]:
        assert p["flow"] in st["nodes"], (project, p["flow"])
        for end in p["from"] + p["to"]:
            assert end in st["nodes"], (project, p["flow"], end)


def test_the_pipe_builder_skips_a_rate_that_is_not_a_diagram_variable():
    """The filter is in build_structure, so check it against the node set the diagram actually gets."""
    import ast
    import delay_audit as da
    names = {"clock": "Clock"}                       # ir names never hold controls: time, time_step, saveper, ...
    terms = da.signed_terms(ast.parse("time()", mode="eval").body, 1, frozenset())
    assert terms == [(1, "time")]                    # the audit still reports it
    assert [f for _, f in terms if f in names] == []  # the diagram drops it
