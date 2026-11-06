"""Headless Chromium smoke test of the built explorers (skipped only when node or Playwright is not installed).
Screenshots: set SD_EXPLORER_SHOTS=<dir>; each project writes into <dir>/<project>/."""
import json
import os
import shutil
import subprocess

import pytest

import _browser

import build_explorer as be
import validate

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SMOKE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "js", "smoke.js")
EXPECT = {
    "bass-b2b-adoption": {"levers": 8, "sliders": 8, "presets": 6, "base_preset": "base", "high": "0.25",
                          "baseline": "base values"},
    "saas-churn-vs-winrate": {"levers": 28, "sliders": 25, "presets": 6, "base_preset": "50/50 split", "high": "0.25",
                              "baseline": "no programme"},
}


@pytest.fixture(scope="module", params=sorted(EXPECT))
def smoke(request, tmp_path_factory):
    node = _browser.node_with_playwright(request, "browser smoke test")
    project = request.param
    d = tmp_path_factory.mktemp("smoke") / project
    shutil.copytree(os.path.join(ROOT, "projects", project), d,
                    ignore=shutil.ignore_patterns("explorer.html", "explorer_parity.json"))
    be.build(str(d))
    shots = os.environ.get("SD_EXPLORER_SHOTS")
    if shots:
        shots = os.path.join(shots, project)
        os.makedirs(shots, exist_ok=True)
    args = [node, SMOKE, str(d / "explorer.html")] + ([shots] if shots else [])
    p = subprocess.run(args, capture_output=True, text=True, timeout=300)
    assert p.returncode == 0, p.stderr[-2000:]
    out = json.loads(p.stdout)
    out["_project"], out["_dir"] = project, str(d)
    return out


def exp(smoke):
    return EXPECT[smoke["_project"]]


def test_loads_without_errors_or_network(smoke):
    assert smoke["console_errors"] == []
    assert smoke["requests"] == []
    assert smoke["title"].endswith("explorer")


def test_every_parameter_has_a_lever(smoke):
    assert smoke["levers"] == exp(smoke)["levers"] and smoke["sliders"] == exp(smoke)["sliders"]


def test_no_outside_range_label_at_base(smoke):
    assert smoke["outside_tags_visible_at_base"] == 0


def test_collapsed_groups(smoke):
    if smoke["_project"] == "saas-churn-vs-winrate":
        assert smoke["groups_closed"] >= 3 and smoke["groups_open"] == 1
    else:
        assert smoke["groups_closed"] == 0


def test_chart_grid_covers_outcome_stocks_and_flows(smoke):
    cfg = json.loads(be.extract_script(open(os.path.join(smoke["_dir"], "explorer.html")).read(), "sd-data"))["charts"]
    assert smoke["charts"] == sum(len(c["vars"]) for c in cfg) >= 4
    assert smoke["chart_cards_about"] == smoke["charts"]


def test_synchronized_crosshair(smoke):
    assert smoke["crosshairs_visible"] == smoke["charts"]
    assert smoke["tooltips_visible"] == 1
    assert smoke["crosshairs_after_escape"] == 0


def test_presets_listed_and_marked(smoke):
    spec = validate.load_spec(os.path.join(smoke["_dir"], "validation.toml"))
    assert smoke["preset_names"] == [p["name"] for p in spec["policies"]]
    assert smoke["presets_pressed_at_base"] == [exp(smoke)["base_preset"]]
    assert smoke["presets_pressed_moved"] == 0
    assert smoke["last_preset_pressed"] == "true"


def test_band_belongs_to_baseline_after_a_change(smoke):
    assert smoke["band_paths_base"] == 2
    assert smoke["band_note_base"].startswith("Monte Carlo")
    assert smoke["band_paths_moved"] == 2
    assert smoke["band_note_moved"].startswith("Baseline band")
    assert "current single run has no band" in smoke["band_note_moved"]
    assert smoke["band_hatched_moved"] == 2 and smoke["band_hatched_base"] == 0
    assert all("Baseline band" in t for t in smoke["band_legend_moved"])
    assert smoke["band_paths_reset"] == 2


def test_moving_a_lever_changes_the_decision_metric(smoke):
    assert smoke["decision_moved"] != smoke["decision_base"]
    assert "vs Baseline: " + exp(smoke)["baseline"] in smoke["delta_moved"]
    assert smoke["decision_reset"] == smoke["decision_base"]


def test_saved_scenarios_compare_up_to_four(smoke):
    assert smoke["saved_after_one"] == 1
    assert smoke["series_a_paths"] == 1
    assert smoke["end_labels"] == ["A"]
    assert smoke["compare_headers"][:4] == ["Metric", "Baseline: " + smoke["baseline_selected"], "Current", "A"]
    assert smoke["saved_after_four"] == 4 and smoke["save_disabled_at_four"]
    assert smoke["saved_after_remove"] == 3


def test_out_of_range_input_is_limited_without_extend(smoke):
    assert smoke["clamped_value"] == exp(smoke)["high"]      # marketing reach rate high end
    assert "validated range" in smoke["clamp_notice"]


def test_extend_shows_banner_and_labels_every_output(smoke):
    assert smoke["banner_visible"]
    assert smoke["banner_text"].strip().startswith("Outside validated range")
    assert smoke["outside_tags_on_tiles"] == smoke["tiles"] > 0
    assert all("outside validated range" in s for s in smoke["chart_subtitles"])


def test_model_limits_one_click_and_keyboard_close(smoke):
    assert smoke["limits_open"] and smoke["limits_has_table"] > 0 and smoke["limits_closed"]


def test_chart_provenance_card(smoke):
    assert "Definition" in smoke["chart_info_text"] and "Source" in smoke["chart_info_text"]


def test_keyboard_crosshair_tooltip(smoke):
    assert "Month 1" in smoke["tooltip_text"]


def test_mobile_layout(smoke):
    sw, cw = smoke["mobile_scroll"]
    assert sw <= cw
    sw, cw = smoke["mobile_scroll_levers"]
    assert sw <= cw
    assert smoke["mobile_tabs_visible"] and smoke["mobile_levers_hidden"] and smoke["mobile_levers_shown"]
    assert smoke["mobile_gutter"] == "16px"


def test_glossary_definition_labelled_explanatory(smoke):
    assert "Explanation (glossary, not part of the validated model)" in smoke["glossary_card"]
    assert "Equation" in smoke["glossary_card"]


def test_compare_against_defaults_to_the_first_policy(smoke):
    spec = validate.load_spec(os.path.join(smoke["_dir"], "validation.toml"))
    first = spec["policies"][0]["name"]
    assert smoke["baseline_selected"].startswith(exp(smoke)["baseline"])
    assert smoke["baseline_selected"].startswith(first) or first == "base"
    assert len(smoke["baseline_options"]) >= len(spec["policies"])
    assert sum("base values" in o for o in smoke["baseline_options"]) == 1


def test_baseline_is_named_everywhere(smoke):
    name = smoke["baseline_selected"]
    assert smoke["baseline_series_label"] == ["Baseline: " + name]
    assert smoke["baseline_cmp_header"] == "Baseline: " + name


def test_switching_baseline_moves_line_deltas_and_table_together(smoke):
    new = smoke["baseline_switched_to"]
    assert new != smoke["baseline_selected"]
    assert smoke["baseline_dashed_after"] != smoke["baseline_dashed_before"]
    assert smoke["baseline_delta_after"] != smoke["baseline_delta_before"]
    assert smoke["baseline_cmp_header_after"] == "Baseline: " + new
    assert smoke["baseline_series_label_after"] == ["Baseline: " + new]
    assert smoke["baseline_consistency"] == {"cells_match": True, "points": True}


def _sentence_case(label):
    words = label.split(" ")
    if not words[0][:1].isupper():
        return False
    for w in words[1:]:
        if w and not (w.islower() or w.isupper() or any(c.isdigit() for c in w)):
            return False
    return True


def test_metric_labels_are_sentence_case(smoke):
    assert smoke["metric_labels"]
    bad = [l for l in smoke["metric_labels"] if not _sentence_case(l)]
    assert bad == []


def _sig_figs(text):
    body = text.lstrip("-").rstrip("KMB")
    digits = body.replace(".", "").lstrip("0")
    return len(digits) if digits else len(body.replace(".", ""))


def test_headline_numbers_use_three_significant_figures(smoke):
    nums = [t for t in smoke["headline_numbers"] if t not in ("undefined", "never (∞)")]
    assert nums
    assert [t for t in nums if _sig_figs(t) != 3] == []


def test_number_rule_examples(smoke):
    assert smoke["format_cases"] == ["37.0M", "542", "36.0", "0.108", "0.140", "1.00K", "1.05K", "2.94M", "0.00", "14.9M"]
