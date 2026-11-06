---
name: sd-explorer
description: Use when a validated system dynamics project needs an interactive, self-contained HTML explorer (levers, charts, stock-and-flow structure, loop strength), when /sd-explorer is invoked, or at gate 10 of /sd-model.
---

# sd-explorer: validated project -> one self-contained interactive page

The same skill runs in Claude Code (`/sd-explorer`) and in Codex (`$sd-explorer`); whatever follows the name is the project(s) to build.

## Overview
Builds `$PROJECTS/<m>/explorer.html`: the validated model re-run live in the browser by a JavaScript engine transpiled from the committed PySD `.py`, with parity to PySD proven at build time. **The page is a view of the validated model, never a second model.** If the build refuses, the project is not ready; fix the project, not the page.

**Tested scope:** two projects of the same model family (`bass-b2b-adoption`, and `saas-churn-vs-winrate`, which extends it). Headless Chromium only. Any construct outside the transpiler's allowlist (`engine/export_js.py` docstring: no SMOOTH/DELAY, lookups, data, subscripts or non-INTEG statefuls) **fails the build loudly**; never hand-patch the emitted JavaScript or the `.py` to get past it.

## Where things are
The engine lives in the **engine home** (`$SD_HOME`); the projects are in the **projects root** (`$PROJECTS`): `--projects-root`, else `SD_PROJECTS_DIR`, else the current folder (the engine home's own `projects/` when started inside it). A project is `$PROJECTS/<m>/`, or any path the user names. Resolve both first, in one Bash call:
```bash
SD_HOME="${SD_FORGE_HOME:-$(head -n1 "$HOME/.config/sd-forge/home" 2>/dev/null)}"; [ -f "$SD_HOME/engine/validate.py" ] && [ -x "$SD_HOME/.venv/bin/python" ] || { echo "sd-forge is not installed: run install-skills.sh in the sd-forge folder (and create its .venv)" >&2; exit 1; }; "$SD_HOME/.venv/bin/python" -I "$SD_HOME/engine/sd_paths.py" check
```
It prints `home=` and `projects_root=`; if it fails, stop and tell the user what it says. Shell variables do not survive between Bash calls: write the printed absolute paths into each command, or repeat the assignments. The page and its records are written into the project folder, never into the engine home. Run the commands from the folder you started in (do not pass `--projects-root` to `check_repo.py`).

## Steps
1. **Intake: one round, up to 4 questions, every one skippable (skip = default).**
   `"$SD_HOME/.venv/bin/python" -I "$SD_HOME/engine/explorer_intake.py" questions "$PROJECTS/<m>"` prints the questions as JSON (projects; decision metric and baseline; levers to expose; audience), each with options and a default.
   - Ask them all in one message. Use the harness's multiple-choice question tool if it has one; otherwise list each question with lettered options and "(default)" marked. Never require a plugin.
   - Map each answer to an option `key`. A skipped question, or an answer that matches no option, takes the default.
   - Record: `"$SD_HOME/.venv/bin/python" -I "$SD_HOME/engine/explorer_intake.py" record "$PROJECTS/<m>" --answers '{"levers": "policy"}'` (only the questions answered).
   - **Unattended** (nobody can answer: scheduled or CI run, the user said "use defaults" or is away): `record "$PROJECTS/<m>" --mode unattended` (same script). Never wait for an answer.
   - "All projects" means: record and build for each validated project.
2. **Delay audit, then build.** First `"$SD_HOME/.venv/bin/python" -I "$SD_HOME/engine/delay_audit.py" "$PROJECTS/<m>"` (skip only if `delay_audit.json` is current; the build stops without it). Then `"$SD_HOME/.venv/bin/python" -I "$SD_HOME/engine/build_explorer.py" "$PROJECTS/<m>"`. The build runs end to end without stopping:
   - It refuses unless `validation_report.md` says Overall PASS, `validation_results.json` has `all_pass`, its recorded sha256 of the model `.mdl` and `.py` equal the files now on disk, and (if `checks.py` exists) `checks_results.json` has `all_pass`.
   - It runs the parity gate against PySD (base, 25 seeded random settings, corners, presets; every stock and output; tolerance 1e-9 on the fixed scale metric) and the link/loop-score gate against `loop_detector` (base and 5 random settings). If the scores do not match, the page shows precomputed base-case values, labelled as such.
   - It writes `explorer.html` and `explorer_parity.json`. Both carry a release stamp: the sha256 of every file the release rests on.
   - If it fails naming variables with no definition, add plain-language entries to `$PROJECTS/<m>/explorer_glossary.toml` (shown as explanatory text, not part of the validated model) and rebuild. Never edit the `.mdl` or `.py` for this.
3. **Verify:** `"$SD_HOME/.venv/bin/python" -I "$SD_HOME/engine/check_repo.py" --require-explorer` exits 0, `"$SD_HOME/.venv/bin/python" -I "$SD_HOME/engine/contrast_check.py"` exits 0, and `"$SD_HOME/.venv/bin/python" -I -m pytest "$SD_HOME/engine/tests" -q --require-browser` passes (it fails, instead of skipping, when Playwright or Chromium is missing).
4. **Report:** page size; parity A/B maximum; link/loop gate numbers and mode (live or precomputed); each intake setting and whether it was chosen or assumed; and what was not verified (real devices, other browsers, screen readers, rendered-pixel contrast).

## Hard rules
| Rule | Detail |
|---|---|
| Refusal gates | Never edit `validation_report.md`, `validation_results.json` or `checks_results.json` to pass them. A model hash mismatch means: re-run `engine/validate.py` (and `checks.py`). |
| Parity metric | Fixed: per series S = max abs(py); A = max abs(js - py) / S <= 1e-9; B pointwise where abs(py) >= 1e-6 S. Never change it or the tolerance to pass. |
| Generated files | `explorer.html` and `explorer_parity.json` are build outputs: never edit them; rebuild. |
| Read-only engine | `engine/validate.py` and `engine/loop_detector.py` change only with the user's approval. |
| Numbers | Every number on the page comes from the run or from the validated files. Intake answers change what the page shows first, never the model, its ranges or the gates. |
| Self-contained | No external URL, font or script; under 3 MB (the build checks). |

## Red flags: stop
- The build refused and you are about to edit a results file, the `.py` or the emitted JS.
- Parity failed "only by a little" and you are looking at the tolerance.
- You are waiting on intake answers in an unattended run.
- The project is not in the tested family and you are about to say it "should work" without building it.

## Files
`engine/...` names are in the engine home (`$SD_HOME/engine/...`).
`engine/build_explorer.py` (build), `engine/explorer_intake.py` (questions, answers), `engine/explorer_release.py` (refusal gate, stamp, shipped-page checks), `engine/export_js.py` (transpiler), `engine/explorer_parity.py`, `engine/explorer_ltm.py` (gates), `engine/explorer_template/` (page), `$PROJECTS/<m>/explorer.toml` (charts, headline; generated once, editable), `$PROJECTS/<m>/explorer_glossary.toml` (plain-language definitions for variables without a model comment; the build fails if a shown variable has neither).
