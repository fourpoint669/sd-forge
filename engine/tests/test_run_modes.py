"""/sd-model run modes (full, checkpoint, express): the pauses of each mode and the skill and command that state them,
the hard rules that hold in every mode, the labelling of a project built without every pause (gate-file records,
[assumed] tags, the summary line, the explorer's Model limits and express banner), and check_repo.py's rule that fails
a checkpoint or express project without them."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

import _browser
import build_explorer as be
import run_mode as rm

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASS = os.path.join(ROOT, "projects", "bass-b2b-adoption")
SKILL = open(os.path.join(ROOT, ".claude", "skills", "sd-model", "SKILL.md"), encoding="utf-8").read()
CMD = open(os.path.join(ROOT, ".claude", "commands", "sd-model.md"), encoding="utf-8").read()


# ---------------------------------------------------------------- the stops of each mode
def test_stops_of_each_mode():
    assert rm.stops("full") == list(range(1, 11))                    # every gate
    assert rm.stops("checkpoint") == [5, rm.END]                     # once after gate 5, once at the end
    assert rm.stops("express") == []                                 # none
    assert rm.DEFAULT == "checkpoint" and set(rm.MODES) == {"full", "checkpoint", "express"}


def _skill_table():
    rows = re.findall(r"^\| (full|checkpoint|express) \| (.+) \|$", SKILL, re.M)
    return dict(rows)


def test_skill_table_states_the_same_stops():
    t = _skill_table()
    assert set(t) == set(rm.MODES)
    assert "every gate" in t["full"]
    assert "once after gate 5" in t["checkpoint"] and "assumptions_register.md" in t["checkpoint"]
    assert "validation.toml" in t["checkpoint"] and "once at the end" in t["checkpoint"]
    assert t["express"].strip() == "none"
    assert "gate 5" in dict(rm.PAUSES["checkpoint"])[5] and "end" in dict(rm.PAUSES["checkpoint"])[rm.END]


def test_mode_is_an_argument_with_default_checkpoint():
    assert "--mode full|checkpoint|express" in SKILL and "No `--mode` means `checkpoint`" in SKILL
    assert re.search(r"argument-hint: .*--mode full\|checkpoint\|express", CMD)
    assert "no `--mode` means `checkpoint`" in CMD and "10 gates" in CMD
    for mode in rm.MODES:
        assert f"`{mode}`" in CMD


def test_hard_rules_hold_in_every_mode():
    for text in (SKILL, CMD):
        assert "gate 1" in text and "names no decision" in text
        assert "gate 7 failure" in text or "failure stops the run" in text
        assert "refusal" in text and "tolerance" in text
    sec = SKILL.split("**Hard rules in every mode**")[1].split("**In `checkpoint`")[0]
    assert "even in `express`" in sec and "never loosen one, in any mode" in sec
    assert "release, parity and loop-score gates" in sec and "check_repo.py" in sec
    assert "Gate 7" in sec and "stops the run" in sec


def test_modes_leave_the_refusal_gates_alone():
    """No mode name appears in the gates that refuse: validate.py, the release gate's refusal path, the parity gate."""
    for f in ("validate.py", "explorer_parity.py", "explorer_ltm.py"):
        assert "run_mode" not in open(os.path.join(ROOT, "engine", f), encoding="utf-8").read()
    rel = open(os.path.join(ROOT, "engine", "explorer_release.py"), encoding="utf-8").read()
    chk = rel.split("def check_release")[1].split("def release_problems")[0]
    assert "run_mode" not in chk and "mode" not in chk.lower()
    be_src = open(os.path.join(ROOT, "engine", "build_explorer.py"), encoding="utf-8").read()
    assert not re.search(r"run_mode[^\n]*(raise|Refused)", be_src)


# ---------------------------------------------------------------- the records
def _insert_record(path, mode, approval):
    t = open(path, encoding="utf-8").read()
    if path.endswith(".toml"):
        t = f"# Run mode: {mode}\n# Approval: {approval}\n" + t
    else:
        head, _, rest = t.partition("\n")
        t = f"{head}\n\n**Run mode:** {mode}\n**Approval:** {approval}\n{rest}"
    open(path, "w", encoding="utf-8").write(t)


def declare(d, mode, label=True, tag=True):
    """Make a copy of a project a `mode` project the way the skill says: records, tags, summary line."""
    for g, files in rm.RECORDS.items():
        for f in files:
            p = os.path.join(d, f)
            if os.path.exists(p):
                _insert_record(p, mode, rm.APPROVAL[mode][g])
    reg = os.path.join(d, "assumptions_register.md")
    t = open(reg, encoding="utf-8").read()
    if tag:
        t = re.sub(r"\| (estimated[^|]*?) \|(?=\s*(?:\n|$))", lambda m: f"| {m.group(1)} {rm.ASSUMED} |", t, flags=re.M)
    open(reg, "w", encoding="utf-8").write(t)
    summ = os.path.join(d, "summary.md")
    s = open(summ, encoding="utf-8").read()
    if label:
        head, _, rest = s.partition("\n")
        s = f"{head}\n\n{rm.LABELS[mode]}\n{rest}"
    open(summ, "w", encoding="utf-8").write(s)
    rehash_spec(d)


def rehash_spec(d):
    """validation.toml gained comments: record its new sha256 the way a gate 7 run after the edit would."""
    p = os.path.join(d, "validation_results.json")
    r = json.load(open(p))
    r["spec_files"]["validation.toml"] = hashlib.sha256(open(os.path.join(d, "validation.toml"), "rb").read()).hexdigest()
    json.dump(r, open(p, "w"), indent=1)


@pytest.fixture
def make(tmp_path):
    n = [0]

    def _make(mode=None, **kw):
        n[0] += 1
        root = tmp_path / f"r{n[0]}"
        d = root / "bass-b2b-adoption"
        shutil.copytree(BASS, d, ignore=shutil.ignore_patterns("explorer.html", "explorer_parity.json"))
        if mode:
            declare(str(d), mode, **kw)
        return str(root), str(d)
    return _make


def edit(path, fn):
    t = open(path, encoding="utf-8").read()
    open(path, "w", encoding="utf-8").write(fn(t))


def check_repo(root):
    p = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "engine", "check_repo.py"), "--projects-root", root],
                       capture_output=True, text=True, cwd=ROOT)
    return p.returncode, p.stdout


@pytest.mark.parametrize("mode", ["checkpoint", "express"])
def test_check_repo_passes_a_labelled_project(make, mode):
    root, d = make(mode)
    assert rm.project_problems(d) == []
    code, out = check_repo(root)
    assert code == 0, out


def test_old_and_full_projects_need_nothing(make):
    root, d = make()                                               # built before modes: no records
    assert rm.read_mode(d) == ("full", []) and rm.project_problems(d) == []
    assert check_repo(root)[0] == 0
    root, d = make("express")                                      # the real project is untouched by the tests
    assert not any(rm.declared(BASS)[f][0] for f in rm.declared(BASS))


@pytest.mark.parametrize("mode", ["checkpoint", "express"])
def test_check_repo_fails_without_the_label(make, mode):
    root, d = make(mode, label=False)
    code, out = check_repo(root)
    assert code == 1 and "summary.md must open" in out and f"{mode}-mode line" in out


def test_check_repo_fails_when_the_label_is_not_first_or_is_edited(make):
    root, d = make("express")
    s = open(os.path.join(d, "summary.md"), encoding="utf-8").read()
    open(os.path.join(d, "summary.md"), "w", encoding="utf-8").write(s.replace(rm.LABELS["express"], "Reviewed.", 1))
    assert check_repo(root)[0] == 1
    root, d = make("express")
    s = open(os.path.join(d, "summary.md"), encoding="utf-8").read().replace("\n\n" + rm.LABELS["express"] + "\n", "\n", 1)
    s += "\n" + rm.LABELS["express"] + "\n"                       # present, but not opening the summary
    open(os.path.join(d, "summary.md"), "w", encoding="utf-8").write(s)
    assert check_repo(root)[0] == 1
    root, d = make("checkpoint")
    s = open(os.path.join(d, "summary.md"), encoding="utf-8").read().replace(rm.LABELS["checkpoint"], rm.LABELS["express"], 1)
    open(os.path.join(d, "summary.md"), "w", encoding="utf-8").write(s)      # the wrong mode's line
    assert check_repo(root)[0] == 1


def test_deleting_one_record_cannot_turn_express_into_full(make):
    root, d = make("express")
    p = os.path.join(d, "01_problem.md")
    t = open(p, encoding="utf-8").read()
    open(p, "w", encoding="utf-8").write(re.sub(r"\*\*Run mode:\*\*[^\n]*\n\*\*Approval:\*\*[^\n]*\n", "", t))
    assert rm.read_mode(d)[0] == "express"
    code, out = check_repo(root)
    assert code == 1 and "01_problem.md does not record 'Run mode: express'" in out
    root, d = make("express", label=False)                          # and with the label gone as well
    for f in os.listdir(d):
        if f.endswith(".md") and f[0] in "0a":
            q = os.path.join(d, f)
            edit(q, lambda t: re.sub(r"\*\*Run mode:\*\*[^\n]*\n\*\*Approval:\*\*[^\n]*\n", "", t))
    assert rm.read_mode(d)[0] == "express"                          # validation.toml still declares it
    assert check_repo(root)[0] == 1


def test_records_must_agree_and_approvals_must_match_the_mode(make):
    root, d = make("express")
    p = os.path.join(d, "02_boundary.md")
    edit(p, lambda t: t.replace("self-approved", "person-approved", 1))
    code, out = check_repo(root)
    assert code == 1 and "02_boundary.md records Approval 'person-approved', express mode needs 'self-approved'" in out
    root, d = make("express")
    p = os.path.join(d, "03_dynamic_hypothesis.md")
    edit(p, lambda t: t.replace("**Run mode:** express", "**Run mode:** checkpoint", 1))
    code, out = check_repo(root)
    assert code == 1 and "different run modes" in out
    root, d = make("express")
    p = os.path.join(d, "04_stock_flow.md")
    edit(p, lambda t: t.replace("**Run mode:** express", "**Run mode:** turbo", 1))
    assert "unknown run mode 'turbo'" in check_repo(root)[1]
    # checkpoint: gate 5 is person-approved, the others self-approved; an unreviewed gate 5 fails
    root, d = make("checkpoint")
    p = os.path.join(d, "assumptions_register.md")
    edit(p, lambda t: t.replace("person-approved", "pending", 1))
    assert "assumptions_register.md records Approval 'pending', checkpoint mode needs 'person-approved'" in check_repo(root)[1]


def test_estimated_parameters_must_be_tagged_assumed(make):
    root, d = make("express", tag=False)
    probs = rm.project_problems(d)
    assert probs and all("is not tagged [assumed]" in p for p in probs)
    n_est = len([1 for _, c in rm._confidence_rows(open(os.path.join(d, "assumptions_register.md")).read())
                 if c.lower().startswith("estimated")])
    assert len(probs) == n_est > 0
    assert check_repo(root)[0] == 1
    root, d = make("express")
    # the register still parses for the explorer with the tag in the Confidence cell
    import explorer_meta as em
    reg = em.parse_register(open(os.path.join(d, "assumptions_register.md")).read())
    assert any(r["confidence"] and rm.ASSUMED in r["confidence"] for r in reg.values())


def test_label_and_limits_text():
    for mode in ("checkpoint", "express"):
        assert rm.label(mode).startswith("**Not reviewed by a person:**") and mode in rm.label(mode)
    assert rm.label("full") is None
    lim = "## Model limits: x\n\nOne.\n\nTwo."
    assert rm.limits_with_label(lim, "full") == lim
    out = rm.limits_with_label(lim, "express")
    assert out.splitlines()[0] == "## Model limits: x" and out.splitlines()[2] == rm.LABELS["express"]
    assert out.endswith("One.\n\nTwo.")
    assert rm.banner_html("express").count(rm.BANNER_CLASS) == 1 and rm.banner_html("checkpoint") == rm.banner_html("full") == ""
    assert subprocess.run([sys.executable, "-I", os.path.join(ROOT, "engine", "run_mode.py"), "label", "express"],
                          capture_output=True, text=True).stdout.strip() == rm.LABELS["express"]


# ---------------------------------------------------------------- the page
def build_page(make, mode):
    root, d = make(mode)
    be.build(d)
    return root, d, open(os.path.join(d, "explorer.html"), encoding="utf-8").read()


@pytest.fixture
def pages(make):
    return {m: build_page(make, m) for m in ("express", "checkpoint", None)}


def test_pages_carry_the_label_and_express_the_banner(pages):
    import explorer_release as er
    for mode in ("express", "checkpoint"):
        root, d, html = pages[mode]
        data = er.page_data(html)
        assert data["run_mode"]["mode"] == mode
        lim = data["model_limits"].splitlines()
        assert lim[0].lower().startswith("## model limits") and lim[2] == rm.LABELS[mode]
        assert (rm.BANNER_CLASS in html) == (mode == "express")
        assert er.shipped_errors(d) == [] and check_repo(root)[0] == 0
    root, d, html = pages[None]
    assert rm.BANNER_CLASS not in html and "Not reviewed by a person" not in html
    assert er.page_data(html)["run_mode"]["mode"] == "full" and check_repo(root)[0] == 0


def test_check_repo_fails_a_page_that_lost_its_banner_or_mode(pages):
    import explorer_release as er
    root, d, html = pages["express"]
    page = os.path.join(d, "explorer.html")
    stripped = re.sub(r'<div class="run-mode-banner".*?</div>\n', "", html, flags=re.S)
    open(page, "w", encoding="utf-8").write(stripped)
    out = check_repo(root)[1]
    assert "must show the not-reviewed banner" in out
    # a page built in another mode than the project records
    root2, d2, html2 = pages["checkpoint"]
    p = os.path.join(d2, "summary.md")
    s = open(p, encoding="utf-8").read().replace(rm.LABELS["checkpoint"], rm.LABELS["express"])
    open(p, "w", encoding="utf-8").write(s)
    for f in rm.RECORDS[1] + rm.RECORDS[2]:
        q = os.path.join(d2, f)
        edit(q, lambda t: t.replace("checkpoint", "express"))
    assert any("built in checkpoint mode but the project records express" in e for e in er.shipped_errors(d2))


def test_express_banner_is_visible_in_the_browser(request, pages, tmp_path):
    node = _browser.node_with_playwright(request, "express banner test")
    js = tmp_path / "banner.js"
    js.write_text("""const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1360, height: 900 } });
  await p.goto('file://' + process.argv[2]); await p.waitForSelector('.tile');
  const o = { n: await p.locator('.run-mode-banner').count(), visible: await p.locator('.run-mode-banner').first().isVisible(),
              text: await p.locator('.run-mode-banner').first().innerText(),
              top: await p.locator('.run-mode-banner').first().evaluate(e => e.getBoundingClientRect().top) };
  await p.emulateMedia({ colorScheme: 'dark' });
  o.dark_visible = await p.locator('.run-mode-banner').first().isVisible();
  await b.close(); console.log(JSON.stringify(o));
})();""", encoding="utf-8")
    out = subprocess.run([node, str(js), os.path.join(pages["express"][1], "explorer.html")], capture_output=True, text=True,
                         timeout=120, env={**os.environ, "NODE_PATH": os.environ.get("NODE_PATH", "") + os.pathsep +
                                           os.path.join(os.path.dirname(ROOT), "node_modules")}, cwd=ROOT)
    assert out.returncode == 0, out.stderr[-1500:]
    o = json.loads(out.stdout)
    assert o["n"] == 1 and o["visible"] and o["dark_visible"] and o["top"] == 0
    assert "Not reviewed by a person" in o["text"] and "express mode" in o["text"]


def test_markdown_formatted_estimated_still_needs_the_tag(tmp_path):
    """Review finding RM-002: **estimated** and `estimated` are estimated, as explorer_meta reads them."""
    import explorer_meta as em
    reg = "| Parameter | Base | Confidence |\n|---|---|---|\n| a | 1 | **estimated** |\n| b | 2 | `estimated` |\n| c | 3 | estimated [assumed] |\n"
    assert all(em.parse_register(reg)[k]["confidence"].strip("*`") == "estimated" for k in ("a", "b"))
    d = tmp_path / "p"
    d.mkdir()
    (d / "assumptions_register.md").write_text(reg)
    (d / "01_problem.md").write_text("# G\n\n**Run mode:** express\n**Approval:** self-approved\n")
    probs = [p for p in rm.project_problems(str(d)) if "not tagged" in p]
    assert len(probs) == 2 and "'a'" in probs[0] and "'b'" in probs[1]


def test_checkpoint_label_makes_no_claim_about_the_final_result():
    """Review finding RM-001: the line is written at gate 9, before the final pause."""
    assert "finished result" not in rm.LABELS["checkpoint"] and "had not been reviewed" in rm.LABELS["checkpoint"]
