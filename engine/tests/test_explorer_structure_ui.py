"""Structure tab in headless Chromium (skipped only when node or Playwright is not installed).
Screenshots: SD_EXPLORER_SHOTS=<dir> writes <dir>/<project>/structure-*.png."""
import json
import os
import shutil
import subprocess

import pytest

import _browser

import build_explorer as be
import validate

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SMOKE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "js", "structure_smoke.js")
LOOPS = {"bass-b2b-adoption": 11, "saas-churn-vs-winrate": 22}


@pytest.fixture(scope="module", params=sorted(LOOPS))
def ui(request, tmp_path_factory):
    node = _browser.node_with_playwright(request)
    project = request.param
    d = tmp_path_factory.mktemp("st") / project
    shutil.copytree(os.path.join(ROOT, "projects", project), d,
                    ignore=shutil.ignore_patterns("explorer.html", "explorer_parity.json"))
    be.build(str(d))
    shots = os.environ.get("SD_EXPLORER_SHOTS")
    if shots:
        shots = os.path.join(shots, project)
        os.makedirs(shots, exist_ok=True)
    p = subprocess.run([node, SMOKE, str(d / "explorer.html")] + ([shots] if shots else []),
                       capture_output=True, text=True, timeout=300)
    assert p.returncode == 0, p.stderr[-2000:]
    out = json.loads(p.stdout)
    html = open(d / "explorer.html", encoding="utf-8").read()
    out["_data"] = json.loads(be.extract_script(html, "sd-data"))
    out["_spec"] = validate.load_spec(str(d / "validation.toml"))
    out["_project"] = project
    return out


def test_no_errors_no_network(ui):
    assert ui["console_errors"] == [] and ui["requests"] == []


def test_structure_is_on_demand(ui):
    assert ui["structure_hidden_by_default"] and ui["structure_svg_before_open"] == 0 and ui["structure_visible"]


def test_svg_loops_equal_declared_loops(ui):
    names = sorted(l["name"] for l in ui["_spec"]["loops"])
    assert len(names) == LOOPS[ui["_project"]]
    assert ui["badge_names"] == names
    assert ui["badge_focusable"] == len(names) and ui["loop_list"] == len(names)


def test_default_view_shows_stocks_flows_and_badges_only(ui):
    assert ui["default_node_kinds"] == ["flow", "stock"]


def test_show_all_draws_every_model_variable_focusable(ui):
    st = ui["_data"]["structure"]
    assert ui["node_ids_all"] == sorted(n["name"] for n in st["nodes"].values())
    assert ui["nodes_focusable"] == ui["nodes_all"] == len(st["nodes"])


def test_delay_marks_equal_the_audit(ui):
    st = ui["_data"]["structure"]
    want = sorted(f"{k['delay']['stock']}|{k['delay']['order']}|{k['delay']['tau']}" for k in st["links"] if k["delay"])
    assert ui["delay_marks"] == want and want


def test_link_polarity_by_line_style_and_glyph(ui):
    styles = ui["link_styles"]
    for key in styles:
        sign, dash = key.split("|")
        assert {"+": "solid", "-": "7 4", "+/-": "9 3 2 3", "0": "1 4"}[sign] == dash, key
    assert ui["sign_glyphs"] == ui["links_drawn"]


def test_legend_explains_every_encoding(ui):
    text = " ".join(ui["legend_items"]).lower()
    for word in ("stock", "flow", "cloud", "auxiliary", "exogenous", "positive", "negative", "delay",
                 "reinforcing", "balancing", "sector", "inactive", "both directions"):
        assert word in text, word


def test_focus_mode(ui):
    assert ui["focus_title"].startswith("Customers")
    assert ui["focus_dimmed"] > 0 and ui["focus_lit"] > 1 and ui["focus_loops_listed"] > 0
    assert ui["focus_cleared"] == 0


def test_loop_isolation(ui):
    lp = next(l for l in ui["_data"]["structure"]["loops"] if l["name"] == ui["first_badge_name"])
    assert ui["isolated_edges"] == len(lp["edges"])
    assert ui["isolated_title"].startswith(lp["name"])
    assert ui["isolation_cleared"] == 0


def test_search_and_sector_collapse_and_zoom(ui):
    assert ui["search_results"] and all("churn" in r.lower() for r in ui["search_results"])
    assert ui["search_focus_title"].lower().startswith(ui["search_results"][0].split(" (")[0].lower())
    assert ui["collapse_hidden"] > 0 and ui["collapse_expanded_attr"] == "false"
    assert ui["zoom_changed"] and ui["minimap"] == 1


def test_cld_mode_has_no_tanks_and_keeps_badges(ui):
    assert ui["cld_tanks"] == 0 and ui["cld_badges"] == LOOPS[ui["_project"]]


def test_mobile(ui):
    assert ui["mobile_structure_visible"]
    sw, cw = ui["mobile_scroll"]
    assert sw <= cw


@pytest.mark.parametrize("view", ["overlap_sfd_wide", "overlap_cld_wide", "overlap_sfd_narrow", "overlap_cld_narrow"])
def test_badges_never_overlap_variable_labels_in_the_rendered_svg(ui, view):
    r = ui[view]
    assert r["badges"] == LOOPS[ui["_project"]] and r["labels"] > 0
    assert r["overlaps"] == []
    assert r["titles_spilling"] == 0


@pytest.mark.parametrize("view", ["fit_sfd_wide", "fit_cld_wide", "fit_sfd_narrow"])
def test_fit_fills_the_canvas_without_clipping(ui, view):
    f = ui[view]
    assert f["inside"]
    assert max(f["fill_w"], f["fill_h"]) >= 0.85


def test_minimap_never_covers_the_diagram(ui):
    assert ui["minimap_in_canvas"] == 0 and ui["minimap_closed"]
    assert ui["minimap_rect"]["visible"] and not ui["minimap_rect"]["overlaps_canvas"]


XSEC_AT_OVERVIEW = {"bass-b2b-adoption": 0, "saas-churn-vs-winrate": 1}


def test_inter_sector_links_hidden_and_pipes_shown_at_the_overview(ui):
    d = ui["xsec_default"]
    assert d["total"] == XSEC_AT_OVERVIEW[ui["_project"]]
    assert d["visible"] == 0 and d["pipes"] > 0 and d["pipes_visible"] == d["pipes"]
    assert ui["xsec_isolated_hidden_on_loop"] == 0


def test_inter_sector_links_appear_on_hover_and_focus(ui):
    if XSEC_AT_OVERVIEW[ui["_project"]] == 0:
        pytest.skip("not applicable: this model has no link between sectors at the overview (counted: "
                    f"{ui['xsec_default']['total']}), so there is nothing to reveal on hover")
    assert ui["xsec_hover"]["visible"] > 0 and ui["xsec_focus"]["visible"] > 0
    assert ui["xsec_after"]["visible"] == 0


GEOM_VIEWS = ["geom_sfd_wide", "geom_cld_wide", "geom_sfd_narrow", "geom_cld_narrow"]


@pytest.mark.parametrize("view", GEOM_VIEWS)
def test_no_line_crosses_a_label_or_sector_title(ui, view):
    g = ui[view]["lines"]
    assert g["lines"] > 0 and g["labels"] > 0
    assert g["hits"] == []


@pytest.mark.parametrize("view", GEOM_VIEWS)
def test_regions_never_overlap(ui, view):
    r = ui[view]["regions"]
    assert r["regions"] > 1 and r["overlapping_pairs"] == 0


@pytest.mark.parametrize("view", GEOM_VIEWS)
def test_no_badge_sits_on_a_pipe(ui, view):
    assert ui[view]["badge_on_pipe"] == []


@pytest.mark.parametrize("view", GEOM_VIEWS)
def test_fit_fills_both_axes(ui, view):
    f = ui[view]["fit"]
    assert f["inside"] and min(f["fill_w"], f["fill_h"]) >= 0.8, f


@pytest.mark.parametrize("view", ["geom_sfd_wide", "geom_sfd_narrow"])
def test_pipes_of_different_flows_never_overlap(ui, view):
    p = ui[view]["pipes"]
    assert p["segments"] > 1
    assert p["hits"] == []


def test_legend_says_how_pipe_colours_read(ui):
    text = " ".join(ui["legend_items"])
    assert "One pipe, one colour" in text and "never on top of each other" in text
