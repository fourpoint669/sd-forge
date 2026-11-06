"""Regressions found by testing the generated pages in a browser. Each script under engine/tests/js was seen failing on the
template before its fix."""
import pathlib
import subprocess

import _browser


def _run_js(request, what, script):
    node = _browser.node_with_playwright(request, what)
    runner = pathlib.Path(__file__).parent / "js" / script
    result = subprocess.run([node, str(runner)], capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_a_decimal_comma_typed_into_a_lever_is_read_as_a_decimal_point(request):
    _run_js(request, "explorer decimal comma", "decimal_comma.js")


def test_no_uncaught_error_when_a_scenario_is_saved_and_the_structure_time_slider_moves(request):
    _run_js(request, "explorer chart crosshair after a saved scenario", "chart_stale_dots.js")


def test_the_page_does_not_scroll_sideways_at_320px_even_with_four_scenarios_saved(request):
    _run_js(request, "explorer reflow at 320px", "reflow_320.js")


def test_an_empty_loop_strength_view_is_explained_instead_of_drawn_blank(request):
    _run_js(request, "explorer empty loop strength", "dom_empty.js")


def test_a_preset_outside_the_validated_ranges_turns_extended_ranges_on(request):
    _run_js(request, "explorer preset outside the validated ranges", "preset_extend.js")


def test_a_flow_that_drains_two_stocks_is_drawn_leaving_both(request):
    _run_js(request, "explorer coflow pipes", "coflow_pipes.js")
