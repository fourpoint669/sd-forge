- **Python {{python_versions}}** (PySD may not support newer). From the repository root:

  ```bash
  python3.12 -m venv .venv && .venv/bin/pip install -r engine/requirements.txt
  ```

- **node.** The parity gate runs the page's engine under node on every build and never skips: without node, the build and every test that builds a page fail.
- **Playwright with Chromium**, for the browser tests. Install Playwright in a folder that node resolves from the repository (for example its parent folder), install Chromium, then check from the repository root that node can load it:

{{pw_steps_block}}

  The check must finish without an error. Without Playwright the browser tests are skipped, not failed: a recorded run of the suite gave {{nopw_passed}} passed and {{nopw_skipped}} skipped ({{nopw_failed}} failed). A release run adds `--require-browser` (or sets `SD_REQUIRE_BROWSER=1`), so a missing browser fails the run instead of being skipped.
