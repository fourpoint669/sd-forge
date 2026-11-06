"""Shared check for the browser tests: node with Playwright and its Chromium installed.

Without them a browser test is skipped, so a plain `pytest` run stays usable on a machine without Playwright. A release
run passes --require-browser (or sets SD_REQUIRE_BROWSER=1) and then a missing browser fails the test instead of
skipping it. The parity and loop-score gates need node in every mode and never skip."""
import os
import shutil
import subprocess

import pytest


def required(config):
    return bool(config.getoption("--require-browser", default=False)) or os.environ.get("SD_REQUIRE_BROWSER") == "1"


PROBE = "const p = require('playwright'); require('fs').accessSync(p.chromium.executablePath());"


def available():
    """Path to node when Playwright loads AND its Chromium is installed (require('playwright') alone succeeds without
    the browser); None otherwise."""
    node = shutil.which("node")
    ok = bool(node) and subprocess.run([node, "-e", PROBE], capture_output=True).returncode == 0
    return node if ok else None


def node_with_playwright(request, what="browser test"):
    """Path to node when the browser is available; otherwise skip, or fail when the browser is required."""
    node = available()
    if node:
        return node
    msg = (f"node + Playwright + Chromium not available: {what} not run. Install: npm install --no-save playwright (in a folder node "
           "resolves from the repo, e.g. its parent), npx playwright install chromium; check: node -e \"require('playwright')\"")
    if required(request.config):
        pytest.fail(msg + " (--require-browser / SD_REQUIRE_BROWSER=1: a missing browser fails this run)", pytrace=False)
    pytest.skip(msg)
