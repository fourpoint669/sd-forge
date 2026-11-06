"""Documentation drift: README.md, docs/QUICKSTART.md and docs/MANUAL.md equal a fresh render of docs/src/ by
engine/build_docs.py (every number read from code, build outputs or real refusal runs); every command, path, flag,
link and slash command in them exists; the templates hold no hand-typed numbers; the screenshot comes from the current
build of the SaaS page and is under the size limit; the PDF copies in docs/pdf are made from the committed text; no
consulting-firm names; line limits hold."""
import json
import os
import re

import build_docs as bd


def test_docs_have_no_drift():
    assert bd.doc_problems() == []


def test_the_checker_catches_drift(tmp_path, monkeypatch):
    facts = bd.all_facts()
    rendered = bd.render(facts)
    stale = dict(rendered)
    stale["docs/MANUAL.md"] = rendered["docs/MANUAL.md"].replace(facts["parity_tol"], "1e-8", 1)
    probs = bd.doc_problems(stale)
    assert any("docs/MANUAL.md is stale" in p for p in probs)


def test_the_checker_catches_missing_paths_flags_and_numbers(monkeypatch):
    rendered = bd.render(bd.all_facts())
    bad = dict(rendered)
    bad["docs/QUICKSTART.md"] += ("\n```bash\n.venv/bin/python -I engine/build_explorer.py projects/<m> --no-such-flag\n"
                                  ".venv/bin/python -I engine/no_such_script.py\n```\nSee `projects/<m>/no_such_file.toml` and "
                                  "[x](no/such/link.md) and /sd-nothing.\n")
    probs = bd.doc_problems(bad)
    assert any("--no-such-flag" in p for p in probs)
    assert any("engine/no_such_script.py" in p for p in probs)
    assert any("no_such_file.toml" in p for p in probs)
    assert any("broken link no/such/link.md" in p for p in probs)
    assert any("/sd-nothing" in p for p in probs)
    assert bd._prose("The page is 290 KB and the tolerance 1e-9.\n```bash\npython3.12 x\n```\n") .count("2") == 1
    assert re.search(r"\d", bd._prose("See gates 1-9, T7b, gate 10 and `1e-9` and {{parity_tol}}.")) is None


def test_every_refusal_message_comes_from_a_real_run():
    t = bd.refusal_messages()
    assert t.count("\n| ") >= 10 and "explorer withheld:" in t and "changed after validation" in t


def test_generated_header_names_the_template():
    for src, dst in bd.TEMPLATES.items():
        first = open(os.path.join(bd.ROOT, dst), encoding="utf-8").readline()
        assert f"from {src}" in first


def test_the_checker_catches_a_message_that_is_not_in_the_code(monkeypatch):
    rendered = bd.render(bd.all_facts())
    orig = bd._read
    monkeypatch.setattr(bd, "_read", lambda rel: orig(rel) + ("\nThe build says `explorer refused for no stated reason`.\n"
                                                             if rel == "docs/src/QUICKSTART.md" else ""))
    probs = bd.doc_problems(rendered)
    assert any("quoted message not found in the code: explorer refused for no stated reason" in p for p in probs)


def _old(path):
    """README.md or docs/MANUAL.md as they were before the Mermaid and table fixes (copies kept in engine/tests/baselines/,
    so the regression checks below do not depend on the git history)."""
    name = {"README.md": "README_baseline.md", "docs/MANUAL.md": "MANUAL_baseline.md"}[path]
    return open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "baselines", name), encoding="utf-8").read()


def test_mermaid_labels_have_no_angle_brackets():
    """(1) projects/<m>/ in a Mermaid label renders as projects// on GitHub; only <br/> may appear."""
    for dst in bd.TEMPLATES.values():
        assert bd.mermaid_problems(open(os.path.join(bd.ROOT, dst), encoding="utf-8").read()) == [], dst
    assert bd.mermaid_problems('```mermaid\nflowchart LR\n  V["projects/&lt;m&gt;/"]\n```\n')
    assert bd.mermaid_problems('```mermaid\nflowchart LR\n  V["model/<name>.py"]\n```\n')
    assert bd.mermaid_problems('```mermaid\nflowchart LR\n  A["one<br/>two"] --> B\n  B -.-> C\n```\n') == []
    old = _old("README.md")                 # the check fails on the README as it was before the fix
    assert any("projects/&lt;m&gt;/" in p for p in bd.mermaid_problems(old))


def test_markdown_tables_are_well_formed():
    """(2) one header, one separator right after it, no stray separator rows or dash lines, equal column counts."""
    for dst in bd.TEMPLATES.values():
        assert bd.table_problems(open(os.path.join(bd.ROOT, dst), encoding="utf-8").read()) == [], dst
    good = "| a | b |\n|---|---|\n| 1 | `x|y` |\n| 2 | a \\| b |\n"
    assert bd.table_problems(good) == []
    assert bd.table_problems("|---|---|\n| a | b |\n|---|---|\n| 1 | 2 |\n|---|---|\n")
    assert bd.table_problems("| a | b |\n|---|---|\n| 1 | 2 | 3 |\n")
    assert bd.table_problems("--- ---\n")
    old = _old("docs/MANUAL.md")            # the check fails on the manual as it was before the fix
    assert any("separator" in p for p in bd.table_problems(old))


def test_gate_table_is_one_clean_table():
    t = bd.gate_table().splitlines()
    assert t[0].startswith("| Gate | ") and re.match(r"^\|(?:-{3}\|)+$", t[1])
    assert not any(re.match(r"^\|(?:-{3}\|)+$", l) for l in t[2:])
    assert [l.split("|")[1].strip().split()[0] for l in t[2:]] == [str(i) for i in range(1, len(t) - 1)]


def test_quickstart_intake_uses_page_labels():
    """(3) display labels from the page, not internal metric names."""
    import tomllib
    q = open(os.path.join(bd.ROOT, "docs", "QUICKSTART.md"), encoding="utf-8").read()
    section = q[q.index("## What you will be asked"):q.index("## What you get")]
    for proj in bd.PROJECTS.values():
        spec = tomllib.load(open(os.path.join(bd.ROOT, proj, "validation.toml"), "rb"))
        for m in spec["montecarlo"]["metrics"]:
            assert not re.search(r"\b" + re.escape(m["name"]) + r"\b", section), m["name"]
    assert "ARR at month 60 vs no programme" in section


def test_prerequisites_are_in_readme_and_quickstart_and_troubleshooting():
    """(4) the same steps in README, QUICKSTART and the MANUAL troubleshooting row, read from one source."""
    texts = {d: open(os.path.join(bd.ROOT, d), encoding="utf-8").read() for d in bd.TEMPLATES.values()}
    for d in ("README.md", "docs/QUICKSTART.md"):
        assert "## Prerequisites" in texts[d]
        for step in bd.PLAYWRIGHT_STEPS + ["python3.12 -m venv .venv", "--require-browser"]:
            assert step in texts[d], (d, step)
    row = next(l for l in texts["docs/MANUAL.md"].splitlines() if l.startswith("| Browser tests skip"))
    for step in bd.PLAYWRIGHT_STEPS + ["--require-browser"]:
        assert step in row
    runs = json.load(open(os.path.join(bd.ROOT, bd.SUITE_RUNS)))["without_playwright"]
    assert f"{runs['passed']} passed and {runs['skipped']} skipped" in texts["README.md"]
    assert runs["summary_line"].startswith(f"{runs['passed']} passed, {runs['skipped']} skipped")


def test_release_command_requires_the_browser():
    """(5) the documented release test command fails, rather than skips, without a browser."""
    for d in ("README.md", "docs/MANUAL.md"):
        assert bd.RELEASE_TEST in open(os.path.join(bd.ROOT, d), encoding="utf-8").read()
    assert "--require-browser" in bd.RELEASE_TEST


def test_pdf_copies_match_their_documents():
    """(7) docs/pdf holds a PDF of each document, made from the text now committed (docs/pdf/pdfs.json)."""
    assert bd.pdf_problems() == []
    man = json.load(open(os.path.join(bd.ROOT, bd.PDF_MANIFEST)))
    assert set(man["documents"]) == set(bd.TEMPLATES.values())
    for rec in man["documents"].values():
        assert open(os.path.join(bd.ROOT, rec["pdf"]), "rb").read(5) == b"%PDF-"


def test_a_pdf_made_from_older_text_or_edited_or_missing_is_reported():
    import copy
    man = json.load(open(os.path.join(bd.ROOT, bd.PDF_MANIFEST)))
    stale = copy.deepcopy(man)
    stale["documents"]["README.md"]["source_sha256"] = "0" * 64
    assert any("made from an older README.md" in p for p in bd.pdf_problems(stale))
    edited = copy.deepcopy(man)
    edited["documents"]["docs/QUICKSTART.md"]["pdf_sha256"] = "0" * 64
    assert any("does not match" in p for p in bd.pdf_problems(edited))
    gone = copy.deepcopy(man)
    del gone["documents"]["docs/MANUAL.md"]
    assert any("no record of docs/pdf/MANUAL.pdf" in p for p in bd.pdf_problems(gone))
    assert len(bd.pdf_problems({"documents": {}})) == 3                # nothing recorded: one problem per document


def test_pdfs_carry_no_local_paths_or_file_links():
    """A relative link printed into a PDF becomes file:///<the maker's home>/...: wrong elsewhere and a leaked path."""
    man = json.load(open(os.path.join(bd.ROOT, bd.PDF_MANIFEST)))
    for rec in man["documents"].values():
        data = open(os.path.join(bd.ROOT, rec["pdf"]), "rb").read()
        for bad in (b"file://", b"/Users/", b"/home/", b"C:\\Users", b"/private/var", b"/private/tmp"):
            assert bad not in data, (rec["pdf"], bad)
        assert b"/Author" not in data, rec["pdf"]
