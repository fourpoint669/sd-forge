"""Link and loop strength on the Structure tab (M3c), in headless Chromium: what is drawn equals the page's own
ltm.js computation (itself gated against loop_detector by the build), follows the scrubber and the levers when live,
and is labelled and frozen at the base case when precomputed."""
import json
import os
import shutil
import subprocess

import pytest

import _browser

import build_explorer as be

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "js", "structure_ltm.js")
CASES = [("bass-b2b-adoption", False), ("saas-churn-vs-winrate", False), ("saas-churn-vs-winrate", True)]


@pytest.fixture(scope="module", params=CASES, ids=["bass-live", "saas-live", "saas-precomputed"])
def ltm(request, tmp_path_factory):
    node = _browser.node_with_playwright(request)
    project, forced = request.param
    d = tmp_path_factory.mktemp("ltm") / project
    shutil.copytree(os.path.join(ROOT, "projects", project), d, ignore=shutil.ignore_patterns("explorer.html", "explorer_parity.json"))
    be.build(str(d), force_ltm_precomputed=forced)
    shots = os.environ.get("SD_EXPLORER_SHOTS")
    if shots:
        shots = os.path.join(shots, project + ("-precomputed" if forced else ""))
        os.makedirs(shots, exist_ok=True)
    p = subprocess.run([node, SCRIPT, str(d / "explorer.html")] + ([shots] if shots else []), capture_output=True, text=True, timeout=300)
    assert p.returncode == 0, p.stderr[-3000:]
    out = json.loads(p.stdout)
    out["_project"], out["_forced"], out["_dir"] = project, forced, str(d)
    return out


def _close(a, b):
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= 1e-12 * max(abs(a), abs(b), 1e-300)


def test_no_errors(ltm):
    assert ltm["console_errors"] == []


def test_mode_and_statement(ltm):
    s = ltm["base"]["statement"]
    if ltm["_forced"]:
        assert ltm["base"]["mode"] == "precomputed" and s.startswith("Precomputed for the base case only")
    else:
        assert ltm["base"]["mode"] == "live" and s.startswith("Live for the current levers")
    assert "not checked against the paper" in s


@pytest.mark.parametrize("snap", ["base", "t30", "moved"])
def test_links_and_badges_show_the_scores_at_the_time_shown(ltm, snap):
    r = ltm[snap]
    assert r["j"] >= 0 and r["links"] and r["badges"]
    for x in r["links"]:
        got = None if x["got"] in ("", None) else float(x["got"])
        assert _close(got, x["want"]), x["e"]
        assert abs(x["width"] - x["wantWidth"]) < 0.01, x["e"]
    for b in r["badges"]:
        got = None if b["got"] in ("", None) else float(b["got"])
        assert _close(got, b["want"]), b["name"]
        if b["wantMeter"] is None:
            assert b["meter"] is None, b["name"]
        else:
            assert abs(b["meter"] - b["wantMeter"]) < 0.01, b["name"]
        assert b["out"] == b["wantOut"], b["name"]
        assert ("not in this view" in b["title"]) == b["wantOut"] and ("not in this view" in b["aria"]) == b["wantOut"], b["name"]
    for x in r["list"]:
        assert x["out"] == ("not in this view" if x["wantOut"] else None), x["name"]


def test_scrubber_and_levers_move_the_scores_only_when_live(ltm):
    assert ltm["t30"]["month"] == 30 and ltm["t30"]["now_x"] != ltm["base"]["now_x"]
    a = [x["got"] for x in ltm["t30"]["badges"]]
    b = [x["got"] for x in ltm["moved"]["badges"]]
    if ltm["_forced"]:
        assert a == b      # precomputed: the base case, whatever the levers
    else:
        assert a != b


def test_dominance_list_equals_the_page_computation(ltm):
    for snap in ("base", "moved"):
        r = ltm[snap]
        assert r["periods"] == [{"start": p["start"], "end": p["end"], "loop": p["loop"]} for p in r["want_periods"]]
        assert r["strongest"]


def test_saas_defaults_to_customer_restricted_and_matches_gate8_at_base(ltm):
    if ltm["_project"] != "saas-churn-vs-winrate":
        assert ltm["base"]["restrict"] is None
        return
    assert ltm["base"]["restrict"] == "on"
    want = json.load(open(os.path.join(ltm["_dir"], "gate8_results.json")))["dominance_customer_loops_base_run"]
    assert [(p["start"], p["end"], p["loop"]) for p in ltm["base"]["periods"]] == [(p["start"], p["end"], p["loop"]) for p in want]
    assert ltm["all_loops"]["periods"] != ltm["base"]["periods"]
    assert any(b["wantOut"] for b in ltm["base"]["badges"]) and not any(b["wantOut"] for b in ltm["all_loops"]["badges"])


def test_loop_strength_is_its_own_side_tab_reachable_without_scrolling(ltm):
    assert ltm["layout_default"] == {"dom_hidden": True, "details_hidden": False}
    assert ltm["key_focus"] == "side-tab-strength"        # arrow keys move between the side tabs
    for key in ("layout", "mobile_layout"):
        lay = ltm[key]
        assert lay["tabs"] == [["Details", "false"], ["Loop strength", "true"]], key
        assert lay["dom_hidden"] is False and lay["details_hidden"] is True, key
        assert lay["periods_after_chart"] and lay["method_after_periods"], key
        assert lay["method_open"] is False, key            # method statement collapsed under the timeline
    assert ltm["layout"]["scroll_top"] == 0 and ltm["layout"]["chart_visible"]


@pytest.mark.parametrize("key", ["layout", "mobile_layout"], ids=["desktop", "375px"])
def test_strength_panel_text_is_never_clipped(ltm, key):
    assert ltm[key]["clipped"] == [], ltm[key]["clipped"]
    assert ltm[key]["overflow"] == [], ltm[key]["overflow"]


def test_legend_explains_the_badge_meter(ltm):
    assert len([x for x in ltm["legend"] if "share among the loops shown" in x]) == 1
    out = [x for x in ltm["legend"] if "not in this view" in x]
    assert len(out) == (1 if ltm["_project"] == "saas-churn-vs-winrate" else 0)   # only a model with a restricted view


def test_mobile(ltm):
    sw, cw = ltm["mobile_scroll"]
    assert sw <= cw
