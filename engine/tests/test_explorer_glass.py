"""Browser regression for the answer-first presentation of shipped explorers."""
import pathlib
import subprocess

import _browser


def test_answer_disclosure_and_release_access(request):
    node = _browser.node_with_playwright(request, "explorer presentation")
    runner = pathlib.Path(__file__).parent / "js" / "glass.js"
    result = subprocess.run([node, str(runner)], capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stderr


def test_primary_controls_fit_and_preserve_baseline(request):
    node = _browser.node_with_playwright(request, "explorer controls")
    runner = pathlib.Path(__file__).parent / "js" / "controls.js"
    result = subprocess.run([node, str(runner)], capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stderr


def test_comparison_disclosure_and_empty_chart(request):
    node = _browser.node_with_playwright(request, "explorer chart states")
    runner = pathlib.Path(__file__).parent / "js" / "states.js"
    result = subprocess.run([node, str(runner)], capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stderr


def test_structure_canvas_remains_usable(request):
    node = _browser.node_with_playwright(request, "explorer responsive structure")
    runner = pathlib.Path(__file__).parent / "js" / "glass_structure.js"
    result = subprocess.run([node, str(runner)], capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stderr


def test_accessibility_preferences_and_touch_targets(request):
    node = _browser.node_with_playwright(request, "explorer accessibility preferences")
    runner = pathlib.Path(__file__).parent / "js" / "preferences.js"
    result = subprocess.run([node, str(runner)], capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stderr


def test_print_solids_and_disclosure_restoration(request):
    node = _browser.node_with_playwright(request, "explorer print")
    runner = pathlib.Path(__file__).parent / "js" / "glass_print.js"
    result = subprocess.run([node, str(runner)], capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stderr


def test_print_uses_current_settings_and_preserves_view(request):
    node = _browser.node_with_playwright(request, "explorer print current state")
    runner = pathlib.Path(__file__).parent / "js" / "print_current.js"
    result = subprocess.run([node, str(runner)], capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stderr


def test_lever_about_cards_use_the_card_width(request):
    node = _browser.node_with_playwright(request, "explorer lever about cards")
    runner = pathlib.Path(__file__).parent / "js" / "lever_about.js"
    result = subprocess.run([node, str(runner)], capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stderr
