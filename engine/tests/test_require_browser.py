"""--require-browser / SD_REQUIRE_BROWSER=1: without them a missing browser skips the browser tests; with either, it fails
the run. Tested by running one real browser test in a subprocess with a stub `node` first on PATH (it cannot load
Playwright), and once with the real node."""
import os
import shutil
import subprocess
import sys

import pytest

import _browser

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ONE = ["engine/tests/test_explorer_intake.py", "-k", "page_is_valid_and_shipped_cleanly and all-skipped"]


def _run(tmp_path, extra=(), env_extra=None, stub=True):
    env = dict(os.environ)
    env.pop("SD_REQUIRE_BROWSER", None)
    if stub:
        b = tmp_path / "bin"
        b.mkdir(exist_ok=True)
        (b / "node").write_text("#!/bin/sh\nexit 1\n")
        (b / "node").chmod(0o755)
        env["PATH"] = str(b) + os.pathsep + env["PATH"]
    env.update(env_extra or {})
    return subprocess.run([sys.executable, "-I", "-m", "pytest", "-q", "-p", "no:cacheprovider", *ONE, *extra],
                          cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)


def test_missing_browser_skips_by_default(tmp_path):
    p = _run(tmp_path)
    assert p.returncode == 0 and "1 skipped" in p.stdout and "failed" not in p.stdout, p.stdout[-800:]


def test_missing_browser_fails_with_the_option(tmp_path):
    p = _run(tmp_path, ["--require-browser"])
    assert p.returncode == 1 and "1 error" in p.stdout and "--require-browser" in p.stdout, p.stdout[-800:]


def test_missing_browser_fails_with_the_environment_variable(tmp_path):
    p = _run(tmp_path, env_extra={"SD_REQUIRE_BROWSER": "1"})
    assert p.returncode == 1 and "1 error" in p.stdout, p.stdout[-800:]


def test_present_browser_passes_with_the_option(tmp_path):
    if not _browser.available():          # same probe as the browser tests: Playwright and its Chromium
        pytest.skip("node + Playwright + Chromium not installed here: the passing mode cannot be shown on this machine")
    p = _run(tmp_path, ["--require-browser"], stub=False)
    assert p.returncode == 0 and "1 passed" in p.stdout, p.stdout[-800:]


def test_playwright_without_chromium_counts_as_missing(tmp_path):
    """require('playwright') alone succeeds without the browser; the check also needs Chromium's executable."""
    node = shutil.which("node")
    if not node or subprocess.run([node, "-e", "require('playwright')"], capture_output=True).returncode:
        pytest.skip("Playwright not installed here: this case cannot be shown on this machine")
    empty = tmp_path / "no-browsers"
    empty.mkdir()
    env = {"PLAYWRIGHT_BROWSERS_PATH": str(empty)}
    p = _run(tmp_path, env_extra=env, stub=False)
    assert p.returncode == 0 and "1 skipped" in p.stdout, p.stdout[-800:]
    p = _run(tmp_path, ["--require-browser"], env_extra=env, stub=False)
    assert p.returncode == 1 and "1 error" in p.stdout and "Chromium" in p.stdout, p.stdout[-800:]


def test_positive_mode_skips_on_ordinary_runs_without_chromium(tmp_path):
    """Review finding 6: without --require-browser, a machine with Playwright but no Chromium skips the positive-mode
    test instead of failing it."""
    env = dict(os.environ, PLAYWRIGHT_BROWSERS_PATH=str(tmp_path / "nonexistent"))
    env.pop("SD_REQUIRE_BROWSER", None)
    p = subprocess.run([sys.executable, "-I", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                        "engine/tests/test_require_browser.py::test_present_browser_passes_with_the_option"],
                       cwd=ROOT, env=env, capture_output=True, text=True, timeout=600)
    assert p.returncode == 0 and "1 skipped" in p.stdout, p.stdout[-800:]
