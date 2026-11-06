"""Render README.md, docs/QUICKSTART.md and docs/MANUAL.md from docs/src/*.md, and check them.

Usage:
  python -I engine/build_docs.py                 render the three documents
  python -I engine/build_docs.py --check         exit 1 if a committed document differs from a fresh render, or if any
                                                 doc check fails (see doc_problems)
  python -I engine/build_docs.py --screenshots   also regenerate docs/img/explorer-annotated.jpg from the committed
                                                 SaaS explorer page (needs node and Playwright)
  python -I engine/build_docs.py --pdfs          also write PDF copies of the three documents to docs/pdf/ (needs node,
                                                 Playwright and the internet, for the pinned marked and mermaid scripts);
                                                 docs/pdf/pdfs.json records which text each PDF was made from, and --check
                                                 fails when a document changed after its PDF was made. A PDF whose
                                                 document, recorded hashes and file are all unchanged is left alone:
                                                 PDF output is not byte-reproducible, so rebuilding it would change the
                                                 file and its hash for nothing. Add --force to rebuild all three
  python -I engine/build_docs.py --record-suite LOG KEY COMMIT COMMAND WHERE
                                                 store the counts from a real pytest run's log in docs/src/suite_runs.json
                                                 (the docs quote the run without Playwright from there)

Templates hold the prose. Every number in the documents comes from a {{placeholder}} filled here from the code (module
constants, docstrings, the page template), from build outputs (explorer_parity.json, explorer.html, validation files)
or from real runs (each refusal message is produced by breaking a temporary copy of a project and calling the build).
The templates may not contain hand-typed quantities; doc_problems() rejects them, and every command, path, flag, link
and slash command in the rendered documents must exist.
"""
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

TEMPLATES = {"docs/src/README.md": "README.md", "docs/src/QUICKSTART.md": "docs/QUICKSTART.md",
             "docs/src/MANUAL.md": "docs/MANUAL.md"}
IMG = "docs/img/explorer-annotated.jpg"
IMG_MANIFEST = "docs/img/screenshots.json"
IMG_SOURCE = "projects/saas-churn-vs-winrate/explorer.html"
IMG_LIMIT = 300 * 1024
PDF_DIR = "docs/pdf"
PDF_MANIFEST = PDF_DIR + "/pdfs.json"
PDF_LIMIT = 2 * 1024 * 1024            # per PDF
SUITE_RUNS = "docs/src/suite_runs.json"
PARTIALS = ["docs/src/_prerequisites.md"]          # rendered first, inserted as {{prerequisites}}
PLAYWRIGHT_STEPS = ["(cd .. && npm install --no-save playwright)", "(cd .. && npx playwright install chromium)",
                    "node -e \"require('playwright')\""]
RELEASE_TEST = ".venv/bin/python -I -m pytest engine/tests -q --require-browser"
LINE_LIMITS = {"README.md": 120, "docs/QUICKSTART.md": 250}
PROJECTS = {"bass": "projects/bass-b2b-adoption", "saas": "projects/saas-churn-vs-winrate"}
PLACEHOLDER = re.compile(r"\{\{([a-z0-9_]+)\}\}")


def _p(*parts):
    return os.path.join(ROOT, *parts)


def _read(rel):
    return open(_p(rel), encoding="utf-8").read()


def _g(x):
    """Numbers as the code holds them, compactly: 1e-09 -> 1e-9, 0.01 -> 0.01, 1000 -> 1000."""
    if isinstance(x, float):
        s = f"{x:g}"
        return re.sub(r"e([+-])0*(\d)", lambda m: "e" + ("-" if m.group(1) == "-" else "") + m.group(2), s)
    return str(x)


def _sig(x, n=2):
    return re.sub(r"e([+-])0*(\d)", lambda m: "e" + ("-" if m.group(1) == "-" else "") + m.group(2), f"{x:.{n - 1}e}") if x else "0"


def _docblock(text, start, end=None):
    i = text.index(start)
    j = text.index(end, i) if end else len(text)
    return text[i:j].rstrip()


# ------------------------------------------------------------------ facts read from code and outputs
def code_facts():
    import contrast_check
    import explorer_config
    import explorer_intake
    import explorer_ltm
    import explorer_parity
    import explorer_release
    import export_js
    import validate
    f = {}
    f["parity_tol"] = _g(explorer_parity.TOL)
    f["pointwise_floor"] = _g(explorer_parity.POINTWISE_FLOOR)
    f["parity_random"] = _g(explorer_parity.N_RANDOM)
    f["parity_seed"] = _g(explorer_parity.SEED)
    f["ltm_tol"] = _g(explorer_ltm.TOL)
    spec = validate.load_spec(_p(PROJECTS["bass"], "validation.toml"))
    f["ltm_random"] = str(len(explorer_ltm.settings(spec)) - 1)
    f["size_limit_mb"] = _g(explorer_release.SIZE_TARGET / 1024 / 1024)
    f["release_tol"] = _g(explorer_release.TOL)
    f["collapse_above"] = _g(explorer_config.COLLAPSE_ABOVE)
    f["mc_min_n"] = _g(validate.MIN_MC_N)
    f["dt_tol_pct"] = _g(validate.DT_TOL * 100)
    f["cons_tol"] = _g(validate.CONS_TOL)
    f["neg_tol"] = _g(validate.NEG_TOL)
    f["peak_steps"] = _g(validate.PEAK_STEPS)
    cc = open(contrast_check.__file__, encoding="utf-8").read()
    f["contrast_text"] = re.search(r'\("text", TEXT, ([\d.]+)\)', cc).group(1)
    f["contrast_graphic"] = re.search(r'\("graphic", GRAPHIC, ([\d.]+)\)', cc).group(1)
    f["contrast_text_ratio"], f["contrast_graphic_ratio"] = f["contrast_text"] + ":1", f["contrast_graphic"] + ":1"
    f["cvd_floor"] = _g(contrast_check.CVD_FLOOR)
    f["normal_floor"] = _g(contrast_check.NORMAL_FLOOR)
    st = _read("engine/explorer_template/structure.js")
    m = re.search(r"function defaults\(\) \{ return \{bind: ([\d.]+), build: ([\d.]+), window: (\d+)\}; \}", st)
    f["pool_bind"], f["pool_build_pct"], f["pool_window"] = _g(float(m.group(1))), _g(float(m.group(2)) * 100), m.group(3)
    app = _read("engine/explorer_template/app.js")
    f["mobile_breakpoint"] = re.search(r'matchMedia\("\(max-width: (\d+)px\)"\)', app).group(1)
    slots = app[app.index("var SLOTS = ["):]
    f["scenario_slots"] = str(slots[:slots.index("];")].count("letter:"))
    f["phone_width"] = re.search(r"viewport: \{ width: (\d+), height: \d+ \}, isMobile", _read("engine/tests/js/structure_ltm.js")).group(1)
    req = _read("engine/requirements.txt")
    f["pysd_version"] = re.search(r"pysd==([\d.]+)", req).group(1)
    f["python_versions"] = re.search(r"Python (3\.\d+ or 3\.\d+)", _read(".claude/skills/sd-model/SKILL.md")).group(1)
    f["img_limit_kb"] = _g(IMG_LIMIT // 1024)
    f["n_intake"] = str(len(explorer_intake.questions([_p(PROJECTS["saas"])])))
    f["export_allowlist"] = _docblock(export_js.__doc__, "Only these constructs", "Ordering never").strip()
    f["validate_tests"] = "```text\n" + _docblock(validate.__doc__, "Tests (thresholds", "Every PySD run").strip() + "\n```"
    f["check_repo_checks"] = "```text\n" + _docblock(_read("engine/check_repo.py").split('"""')[1], "Checks:").strip() + "\n```"
    f["build_steps"] = "```text\n" + _docblock(_read("engine/build_explorer.py").split('"""')[1], "Steps (").strip() + "\n```"
    f["release_doc"] = "```text\n" + explorer_release.__doc__.strip() + "\n```"
    return f


def project_facts():
    import explorer_meta
    f = {}
    for key, rel in PROJECTS.items():
        d = _p(rel)
        par = json.load(open(os.path.join(d, "explorer_parity.json")))
        spec = tomllib.load(open(os.path.join(d, "validation.toml"), "rb"))
        f[f"{key}_name"] = os.path.basename(rel)
        f[f"{key}_page_kb"] = str(round(os.path.getsize(os.path.join(d, "explorer.html")) / 1024))
        f[f"{key}_parity_a"] = _sig(par["max_scale_rel"])
        f[f"{key}_parity_b"] = _sig(par["max_pointwise_rel"])
        f[f"{key}_headline"] = _sig(par["headline"]["max_rel"])
        f[f"{key}_parity_runs"] = str(par["n_runs"])
        f[f"{key}_parity_series"] = str(par["n_series"])
        f[f"{key}_ltm_link"] = _sig(par["ltm"]["end_to_end"]["max_link"])
        f[f"{key}_ltm_loop"] = _sig(par["ltm"]["end_to_end"]["max_loop"])
        f[f"{key}_ltm_runs"] = str(par["ltm"]["n_runs"])
        f[f"{key}_ltm_mode"] = par["ltm"]["mode"]
        f[f"{key}_mc_n"] = str(spec["montecarlo"]["n"])
        f[f"{key}_loops"] = str(len(json.load(open(os.path.join(d, "loop_dominance.json")))["loops"]))
        f[f"{key}_dt"] = _g(spec["model"]["time_step"])
        f[f"{key}_time_unit"] = spec["model"]["time_unit"].lower()
        f[f"{key}_levers"] = str(len(spec["parameters"]))
        f[f"{key}_objective"] = spec["policy"]["objective"]
        lim = explorer_meta.model_limits(open(os.path.join(d, "summary.md"), encoding="utf-8").read())
        f[f"{key}_limits"] = "\n".join(lim.splitlines()[1:]).strip()      # verbatim, without its own heading
        v = json.load(open(os.path.join(d, "validation_results.json")))
        f[f"{key}_validation"] = "all tests pass" if v.get("all_pass") else "FAILING"
    f["n_projects"] = str(len(PROJECTS))
    f["checks_projects"] = ", ".join(f"`{os.path.basename(r)}`" for r in PROJECTS.values() if os.path.exists(_p(r, "checks.py"))) or "none"
    for k in ("dt", "mc_n", "time_unit"):        # stated once for every shipped project only when they agree
        vals = {f[f"{p}_{k}"] for p in PROJECTS}
        if len(vals) != 1:
            raise ValueError(f"projects differ in {k}: {vals}; the manual's glossary states one value")
        f[f"common_{k}"] = vals.pop()
    return f


def intake_table():
    import explorer_intake
    rows = ["| Question | Options (default first) | If skipped |", "|---|---|---|"]
    for q in explorer_intake.questions([_p(PROJECTS["saas"])]):
        opts = "<br>".join(f"`{o['key']}`: {o['label']}. {o['description']}" for o in q["options"])
        dflt = next(o["label"] for o in q["options"] if o["key"] == q["default"])
        rows.append(f"| {q['question']} | {opts} | {dflt} |")
    return "\n".join(rows)


def intake_plain():
    import explorer_intake
    out = []
    for q in explorer_intake.questions([_p(PROJECTS["saas"])]):
        dflt = next(o["label"].replace(" (default)", "") for o in q["options"] if o["key"] == q["default"])
        others = ", ".join(o["label"] for o in q["options"] if o["key"] != q["default"])
        out.append(f"- **{q['question']}** Default: {dflt}. Other choices: {others}.")
    return "\n".join(out)


def _copy(rel, tmp):
    d = os.path.join(tmp, os.path.basename(rel) + "-" + str(len(os.listdir(tmp))), os.path.basename(rel))
    shutil.copytree(_p(rel), d)
    return d


def _edit_json(path, **kw):
    r = json.load(open(path))
    for k, v in kw.items():
        if v is None:
            r.pop(k, None)
        else:
            r[k] = v
    json.dump(r, open(path, "w"))


def _rewrite(path, fn):
    txt = open(path, encoding="utf-8").read()
    with open(path, "w", encoding="utf-8") as f:
        f.write(fn(txt))


def refusal_messages():
    """Each refusal and build failure, produced for real on a broken temporary copy of a project."""
    import build_explorer as be
    cases = [
        ("validation_report.md does not say Overall PASS", "bass",
         lambda d: _rewrite(os.path.join(d, "validation_report.md"), lambda t: t.replace("Overall: **PASS**", "Overall: **FAIL**"))),
        ("validation_results.json all_pass is false", "bass", lambda d: _edit_json(os.path.join(d, "validation_results.json"), all_pass=False)),
        ("validation_results.json is missing", "bass", lambda d: os.remove(os.path.join(d, "validation_results.json"))),
        ("validation_results.json has no model hashes (validated before hashes were recorded)", "bass",
         lambda d: _edit_json(os.path.join(d, "validation_results.json"), model_files=None)),
        ("the model .py (or .mdl) changed after validation", "bass",
         lambda d: _rewrite(glob.glob(os.path.join(d, "model", "*.py"))[0], lambda t: t + "\n")),
        ("checks.py exists but checks_results.json is missing", "saas", lambda d: os.remove(os.path.join(d, "checks_results.json"))),
        ("checks_results.json all_pass is false", "saas", lambda d: _edit_json(os.path.join(d, "checks_results.json"), all_pass=False)),
        ("a parameter has no row in assumptions_register.md", "bass",
         lambda d: _rewrite(os.path.join(d, "assumptions_register.md"),
                            lambda t: "\n".join(l for l in t.splitlines() if not l.startswith("| win rate")) + "\n")),
        ("a shown variable has no model comment and no glossary entry", "bass",
         lambda d: _rewrite(os.path.join(d, "explorer_glossary.toml"),
                            lambda t: re.sub(r'\[variables\."churn rate monthly"\]\ndefinition = "[^"]*"\n', "", t))),
        ("explorer.toml names a variable the model does not have", "bass",
         lambda d: _rewrite(os.path.join(d, "explorer.toml"),
                            lambda t: t + '\n[[charts]]\nid = "x"\nkind = "grid"\ntitle = "x"\nvars = ["No Such Variable"]\n')),
        ("explorer_intake.toml holds an answer that is not an option", "bass",
         lambda d: _rewrite(os.path.join(d, "explorer_intake.toml"), lambda t: t.replace('value = "decision-makers"', 'value = "everyone"'))),
    ]
    rows = ["| Condition | Error | Exact message (from a real run on a broken copy of the project) |", "|---|---|---|"]
    with tempfile.TemporaryDirectory() as tmp:
        for cond, key, breaker in cases:
            d = _copy(PROJECTS[key], tmp)
            breaker(d)
            try:
                be.build(d)
                raise RuntimeError(f"build did not fail for: {cond}")
            except (be.Refused, Exception) as e:  # noqa: BLE001 - every failure type is recorded with its class name
                if isinstance(e, RuntimeError) and str(e).startswith("build did not fail"):
                    raise
                rows.append(f"| {cond} | `{type(e).__name__}` | `{str(e)}` |")
    return "\n".join(rows)


def check_repo_example():
    """The check_repo.py error for a model edited after validation, from a real run on a temporary copy."""
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "projects")
        shutil.copytree(_p(PROJECTS["bass"]), os.path.join(root, "bass-b2b-adoption"))
        mdl = glob.glob(os.path.join(root, "bass-b2b-adoption", "model", "*.mdl"))[0]
        _rewrite(mdl, lambda t: t + "\n")
        out = subprocess.run([sys.executable, "-I", _p("engine", "check_repo.py"), "--projects-root", root],
                             cwd=ROOT, capture_output=True, text=True).stdout
    lines = [l.replace(tmp + os.sep, "<tmp>/").replace("\\", "/") for l in out.splitlines() if l.startswith("ERR") and "changed after validation" in l]
    return "```text\n" + "\n".join(lines[:1]) + "\n```"


def source_messages():
    """Failures that cannot be produced from the shipped projects: quoted from the source as written."""
    out = []
    for rel, pat in (("engine/export_js.py", r'raise Unsupported\((f?"[^"]+")'),
                     ("engine/build_explorer.py", r'raise RuntimeError\((f?"[^"]+")'),
                     ("engine/explorer_ltm.py", r'raise RuntimeError\((f?"[^"]+")'),
                     ("engine/explorer_parity.py", r'raise RuntimeError\((f?"[^"]+")')):
        for m in re.finditer(pat, _read(rel)):
            out.append(f"| `{rel}` | `{m.group(1)}` |")
    return "| Source | Message as written in the code (`{...}` is filled at run time) |\n|---|---|\n" + "\n".join(sorted(set(out)))


def gate_table():
    """The gates table of the sd-model skill: its header row and the table rows that follow it, nothing else."""
    lines = _read(".claude/skills/sd-model/SKILL.md").splitlines()
    i = next(k for k, l in enumerate(lines) if l.startswith("| Gate | "))
    rows = []
    for l in lines[i:]:
        if not l.startswith("|"):
            break
        rows.append(l)
    return "\n".join(rows)


def run_mode_facts():
    import run_mode as rm
    rows = ["| Mode | Pauses for the person |", "|---|---|"]
    for m in rm.MODES:
        pauses = "after every gate, gates 1-10" if m == "full" else "; ".join(w for _, w in rm.PAUSES[m]) or "none"
        rows.append(f"| `{m}` | {pauses} |")
    rec = ["| Where | What must be there |", "|---|---|",
           "| " + ", ".join(f"`{f}`" for fs in rm.RECORDS.values() for f in fs) + " | `**Run mode:** <mode>` and `**Approval:**` (`" + rm.SELF + "`; checkpoint: `" + rm.PERSON + "` for the two gate 5 files); `validation.toml` as `#` comments |",
           f"| `assumptions_register.md` | `{rm.ASSUMED}` in the Confidence cell of every `estimated` parameter |",
           "| `summary.md` | the mode's line, first after the title |",
           "| `explorer.html` | the same line at the top of Model limits; express: also a banner (`" + rm.BANNER_CLASS + "`) |"]
    return {"run_modes_table": "\n".join(rows), "run_mode_records": "\n".join(rec),
            "run_mode_labels": "\n\n".join(f"- `{m}`: {rm.LABELS[m]}" for m in rm.LABELS)}


def gate_protections():
    import explorer_release as er
    rows = ["| The gates protect against | How (the check that does it) |", "|---|---|"]
    rows += [f"| {a} | {b} |" for a, b in er.PROTECTIONS]
    return "\n".join(rows) + "\n\nThey do not protect against:\n\n" + "\n".join(f"- {x}" for x in er.NOT_PROTECTED)


def stamp_files():
    """The files each shipped page's release stamp covers, read from its explorer_parity.json."""
    rows = ["| Project | Stamped files (sha256 recorded at build time, re-checked by `check_repo.py`) |", "|---|---|"]
    for rel in PROJECTS.values():
        files = sorted(json.load(open(_p(rel, "explorer_parity.json")))["release"]["files"])
        rows.append(f"| `{os.path.basename(rel)}` | " + ", ".join(f"`{f}`" for f in files) + " |")
    return "\n".join(rows)


def test_files():
    rows = ["| Test file | What it checks (its docstring) |", "|---|---|"]
    for p in sorted(glob.glob(_p("engine", "tests", "test_*.py"))):
        m = re.match(r'\s*"""(.*?)(?:"""|\n\n)', open(p, encoding="utf-8").read(), re.S)
        doc = " ".join(m.group(1).split()).replace("|", "\\|") if m else ""
        rows.append(f"| `engine/tests/{os.path.basename(p)}` | {doc} |")
    return "\n".join(rows)


def record_suite(log, key, commit, command, where):
    """Store the counts from a real pytest run (its final summary line) so the docs can quote them."""
    last = [l for l in open(log, encoding="utf-8").read().splitlines() if re.search(r"\d+ passed", l)][-1]
    counts = {k: int(n) for n, k in re.findall(r"(\d+) (passed|skipped|failed|errors?)", last)}
    runs = json.load(open(_p(SUITE_RUNS))) if os.path.exists(_p(SUITE_RUNS)) else {}
    runs[key] = {"commit": commit, "command": command, "where": where, "summary_line": last.strip(),
                 "passed": counts.get("passed", 0), "skipped": counts.get("skipped", 0),
                 "failed": counts.get("failed", 0) + counts.get("error", 0) + counts.get("errors", 0)}
    with open(_p(SUITE_RUNS), "w", encoding="utf-8", newline="\n") as f:
        json.dump(runs, f, indent=1, sort_keys=True)
        f.write("\n")


def suite_facts():
    r = json.load(open(_p(SUITE_RUNS)))["without_playwright"]
    return {"nopw_passed": str(r["passed"]), "nopw_skipped": str(r["skipped"]), "nopw_failed": str(r["failed"]),
            "nopw_commit": r["commit"], "nopw_where": r["where"]}


def all_facts():
    f = {}
    f.update(code_facts())
    f.update(project_facts())
    f["intake_table"] = intake_table()
    f["intake_plain"] = intake_plain()
    f["refusal_table"] = refusal_messages()
    f["check_repo_example"] = check_repo_example()
    f["source_messages"] = source_messages()
    f["gate_table"] = gate_table()
    f.update(run_mode_facts())
    f.update(suite_facts())
    f["pw_steps_block"] = "\n\n".join("  ```bash\n  " + c + "\n  ```" for c in PLAYWRIGHT_STEPS)
    f["pw_steps_inline"] = (f"`{PLAYWRIGHT_STEPS[0]}`, then `{PLAYWRIGHT_STEPS[1]}`; check from the repository root with "
                            f"`{PLAYWRIGHT_STEPS[2]}`")
    f["release_test"] = RELEASE_TEST
    f["test_files"] = test_files()
    f["stamp_files"] = stamp_files()
    f["gate_protections"] = gate_protections()
    f["saas_intake_toml"] = "```toml\n" + _read(PROJECTS["saas"] + "/explorer_intake.toml").strip() + "\n```"
    return f


# ------------------------------------------------------------------ render and check
def render(facts):
    facts = dict(facts)
    for src in PARTIALS:
        key = os.path.basename(src)[1:-3]
        facts[key] = PLACEHOLDER.sub(lambda m: facts[m.group(1)], _read(src)).rstrip("\n")
    out = {}
    for src, dst in TEMPLATES.items():
        t = _read(src)
        missing = sorted(set(PLACEHOLDER.findall(t)) - set(facts))
        if missing:
            raise KeyError(f"{src}: unknown placeholders {missing}")
        body = PLACEHOLDER.sub(lambda m: facts[m.group(1)], t)
        out[dst] = ("<!-- Generated by engine/build_docs.py from " + src + ". Edit the template, then run "
                    "`python -I engine/build_docs.py`. -->\n" + body)
    return out


QUANTITY = re.compile(r"\d")
ALLOWED_DIGITS = re.compile(r"\b(?:[Gg]ates?) \d+(?:-\d+)?\b|\bT\d+[bc]?\b|\b[A-C]\.|\bmarkers? \d+(?:-\d+)?\b|\bsha256\b")


def _prose(text):
    """Template text with code, placeholders, list markers and html comments removed."""
    keep, fence = [], None                      # code blocks are dropped; Mermaid diagrams count as prose
    for line in text.splitlines():
        if fence is None and line.lstrip().startswith("```"):
            fence = line.strip()[3:] or "text"
            continue
        if fence is not None and line.strip() == "```":
            fence = None
            continue
        if fence is None or fence == "mermaid":
            keep.append(line)
    text = "\n".join(keep)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", "", text)
    text = PLACEHOLDER.sub("", text)
    text = re.sub(r"\]\([^)]*\)", "]", text)
    text = re.sub(r"^\s*\d+\.\s", "", text, flags=re.M)
    return ALLOWED_DIGITS.sub("", text)


def mermaid_problems(text):
    """Angle brackets in a Mermaid label are read as HTML (projects/<m>/ renders as projects//); only <br/> is allowed."""
    out = []
    for block in re.findall(r"```mermaid\n(.*?)```", text, re.S):
        for line in block.splitlines():
            bare = line.replace("<br/>", " ")
            if re.search(r"[<>]|&lt;|&gt;|&#", bare.replace("-->", "").replace("-.->", "").replace("->", "")):
                out.append(f"Mermaid label with an angle bracket: {line.strip()}")
    return out


def _cells(line):
    """Column count of a table row, ignoring pipes inside code spans."""
    return len(re.sub(r"`[^`]*`", "", line.replace("\\|", "")).strip().strip("|").split("|"))


def table_problems(text):
    """Every Markdown table: header, one separator row right after it, no other separator rows, same column count."""
    out, rows, fence = [], [], False
    sep = re.compile(r"^\|(?:\s*:?-{3,}:?\s*\|)+\s*$")
    for line in text.splitlines() + [""]:
        if line.lstrip().startswith("```"):
            fence = not fence
        if not fence and line.startswith("|"):
            rows.append(line)
            continue
        if rows:
            if len(rows) < 2 or not sep.match(rows[1]) or sep.match(rows[0]):
                out.append(f"table without a header and separator row: {rows[0][:60]}")
            extra = [r for r in rows[2:] if sep.match(r)]
            if extra:
                out.append(f"stray separator row inside a table starting {rows[0][:60]}")
            n = {_cells(r) for r in rows if not sep.match(r)}
            if len(n) > 1:
                out.append(f"rows with different column counts {sorted(n)} in table starting {rows[0][:60]}")
            rows = []
        if not fence and re.match(r"^\s*-{3}(?:\s+-{3})+\s*$", line):
            out.append(f"stray dashes line: {line.strip()}")
    return out


def _script_text(token):
    p = _p(token)
    return open(p, encoding="utf-8").read() if os.path.isfile(p) else ""


def _exists(token, projects):
    token = token.rstrip(".,:;")
    if token.startswith(".venv/"):
        return True            # created by the documented setup command, not part of the repository
    top = token.split("/")[0]
    if top in ROOT_ENTRIES:
        bases = [""]
    else:                                       # relative to a project folder, the engine or the library
        bases = ["projects/" + n + "/" for n in projects] + ["engine/", "library/", "raw/"]
    for b in bases:                             # a <placeholder> segment matches anything
        if glob.glob(_p(re.sub(r"<[^>/]+>", "*", b + token))):
            return True
    return token.rstrip("/") in IGNORED


ROOT_ENTRIES = set(os.listdir(ROOT)) | {".venv"}
IGNORED = {l.strip().rstrip("/") for l in open(os.path.join(ROOT, ".gitignore")).read().splitlines() if l.strip() and not l.startswith("#")}
PATHLIKE = re.compile(r"^(?:\.?[\w.<>-]+/)+[\w.<>*-]*$|^[\w.-]+\.(?:py|md|toml|json|html|js|csv|css|txt|png|jpg|mdl)$")


def doc_problems(rendered=None):
    """Every problem in the documents: stale renders, missing paths/commands/flags/links, hand-typed numbers."""
    probs = []
    facts = None
    if rendered is None:
        facts = all_facts()
        rendered = render(facts)
    projects = [os.path.basename(v) for v in PROJECTS.values()]
    for src in PARTIALS:
        for line in _prose(_read(src)).splitlines():
            if QUANTITY.search(line):
                probs.append(f"{src}: hand-typed number in prose (use a placeholder): {line.strip()[:100]}")
    for src, dst in TEMPLATES.items():
        if not os.path.exists(_p(dst)) or _read(dst) != rendered[dst]:
            probs.append(f"{dst} is stale: run python -I engine/build_docs.py")
        for line in _prose(_read(src)).splitlines():
            if QUANTITY.search(line):
                probs.append(f"{src}: hand-typed number in prose (use a placeholder): {line.strip()[:100]}")
        text = rendered[dst]
        if dst in LINE_LIMITS and text.count("\n") + 1 > LINE_LIMITS[dst]:
            probs.append(f"{dst}: {text.count(chr(10)) + 1} lines (limit {LINE_LIMITS[dst]})")
        if re.search(r"\binterview", text, re.I):
            probs.append(f"{dst}: interview framing")
        probs += [f"{dst}: {p}" for p in mermaid_problems(text) + table_problems(text)]
        base = os.path.dirname(dst)
        for link in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", text):
            if not link.startswith(("http://", "https://", "mailto:")) and not os.path.exists(_p(base, link)):
                probs.append(f"{dst}: broken link {link}")
        for cmd in set(re.findall(r"(?<![\w/`])/(sd-[a-z-]+)\b", text)):
            if not os.path.exists(_p(".claude", "commands", cmd + ".md")):
                probs.append(f"{dst}: slash command /{cmd} has no .claude/commands/{cmd}.md")
        code = re.findall(r"```(?:bash|sh)\n(.*?)```", text, re.S) + re.findall(r"`([^`\n]+)`", text)
        for chunk in code:
            for line in chunk.splitlines():
                toks = line.split()
                script = next((t for t in toks if re.match(r"^(?:engine|projects)/[\w/.-]+\.(?:py|js)$", t)), None)
                third_party = any(t.lstrip("(") in ("npm", "npx") for t in toks)
                for t in toks:
                    t = t.strip("'\"")
                    if t.startswith("--") and re.match(r"^--[a-z][a-z-]+$", t):
                        if third_party:
                            continue                     # npm/npx flags belong to those tools
                        if script:
                            if t not in _script_text(script):
                                probs.append(f"{dst}: flag {t} not in {script}")
                        elif re.search(r"\bpytest\b", line):
                            if t not in _read("engine/tests/conftest.py"):
                                probs.append(f"{dst}: pytest option {t} not defined in engine/tests/conftest.py")
                        elif not any(t in _script_text(s) for s in glob.glob(_p("engine", "*.py"))):
                            probs.append(f"{dst}: flag {t} not found in any engine script")
                    elif PATHLIKE.match(t) and not t.startswith(("http", "-")) and ("/" in t or "." in t):
                        if "/" not in t and not os.path.exists(_p(t)):
                            continue         # a bare file name (e.g. summary.md) is described relative to a project
                        if not _exists(t, projects):
                            probs.append(f"{dst}: path does not exist: {t}")
    # every message quoted by hand in a template exists in the code (split at "...")
    code_text = "".join(open(p, encoding="utf-8").read() for p in
                        glob.glob(_p("engine", "*.py")) + glob.glob(_p("engine", "explorer_template", "*.js")))
    for src in list(TEMPLATES) + PARTIALS:
        for span in re.findall(r"`([^`\n]+)`", _read(src)):
            if " " not in span or "<" in span or "{{" in span or span.startswith((".venv", "python", "/", "node ", "engine/", "--",
                                                                                     "npm ", "npx ", "(cd ", "SD_")):
                continue
            for frag in (x.strip() for x in span.split("...")):
                if len(frag) >= 6 and frag not in code_text:
                    probs.append(f"{src}: quoted message not found in the code: {frag}")
    # screenshot from the current build, within the size limit
    try:
        man = json.load(open(_p(IMG_MANIFEST)))
        if man.get("source") != IMG_SOURCE or man.get("source_sha256") != hashlib.sha256(open(_p(IMG_SOURCE), "rb").read()).hexdigest():
            probs.append(f"{IMG} was taken from an older build of {IMG_SOURCE}: run python -I engine/build_docs.py --screenshots")
        if hashlib.sha256(open(_p(IMG), "rb").read()).hexdigest() != man.get("image_sha256"):
            probs.append(f"{IMG} does not match {IMG_MANIFEST}")
        if os.path.getsize(_p(IMG)) > IMG_LIMIT:
            probs.append(f"{IMG} is {os.path.getsize(_p(IMG))} bytes (limit {IMG_LIMIT})")
    except (OSError, ValueError) as e:
        probs.append(f"screenshot manifest unreadable: {e}")
    probs += pdf_problems()
    return probs


def _pdf_sources():
    """document path -> PDF path, for the three rendered documents."""
    return {dst: f"{PDF_DIR}/{os.path.splitext(os.path.basename(dst))[0]}.pdf" for dst in TEMPLATES.values()}


def pdf_problems(man=None):
    """Problems with the PDF copies: each exists, is a PDF within the size limit, is the file the manifest recorded, and
    was made from the document text as it is now."""
    probs = []
    try:
        man = json.load(open(_p(PDF_MANIFEST))) if man is None else man
    except (OSError, ValueError) as e:
        return [f"PDF manifest {PDF_MANIFEST} unreadable ({e}): run python -I engine/build_docs.py --pdfs"]
    rec = man.get("documents", {})
    for doc, pdf in _pdf_sources().items():
        r = rec.get(doc)
        if not isinstance(r, dict) or r.get("pdf") != pdf:
            probs.append(f"{PDF_MANIFEST} has no record of {pdf}: run python -I engine/build_docs.py --pdfs")
            continue
        try:
            data = open(_p(pdf), "rb").read()
        except OSError:
            probs.append(f"{pdf} is missing: run python -I engine/build_docs.py --pdfs")
            continue
        if not data.startswith(b"%PDF-"):
            probs.append(f"{pdf} is not a PDF")
        if len(data) > PDF_LIMIT:
            probs.append(f"{pdf} is {len(data)} bytes (limit {PDF_LIMIT})")
        if hashlib.sha256(data).hexdigest() != r.get("pdf_sha256"):
            probs.append(f"{pdf} does not match {PDF_MANIFEST}")
        if hashlib.sha256(open(_p(doc), "rb").read()).hexdigest() != r.get("source_sha256"):
            probs.append(f"{pdf} was made from an older {doc}: run python -I engine/build_docs.py --pdfs")
    return probs


def _file_sha256(path):
    return hashlib.sha256(open(_p(path), "rb").read()).hexdigest()


def stale_pdfs(man, sources, force=False):
    """The documents whose PDF has to be made again: its record is missing or for another path, the PDF itself is
    gone or no longer the file that was recorded, or the document has changed since. A PDF that is current is left
    alone, because rendering is not byte-reproducible and rebuilding it would change the file and its recorded hash
    while the text it was made from did not change. force takes all of them."""
    rec = (man or {}).get("documents") or {}
    out = {}
    for doc, pdf in sources.items():
        r = rec.get(doc)
        if force or not isinstance(r, dict) or r.get("pdf") != pdf or not os.path.exists(_p(pdf)):
            out[doc] = pdf
            continue
        try:
            current = (r.get("source_sha256") == _file_sha256(doc) and r.get("pdf_sha256") == _file_sha256(pdf))
        except OSError:
            current = False
        if not current:
            out[doc] = pdf
    return out


def pdfs(force=False):
    node = shutil.which("node")
    if not node:
        raise RuntimeError("node not found: the PDFs need node and Playwright")
    sources = _pdf_sources()
    try:
        man = json.load(open(_p(PDF_MANIFEST), encoding="utf-8"))
    except (OSError, ValueError):
        man = {}
    stale = stale_pdfs(man, sources, force)
    for doc in sources:
        if doc not in stale:
            print("kept", sources[doc], "(unchanged since it was made)")
    if stale:
        subprocess.run([node, _p("engine", "docs_pdfs.js"), _p(PDF_DIR)] + [_p(d) for d in stale], check=True, timeout=600)
    man = {"made_by": "engine/build_docs.py --pdfs (engine/docs_pdfs.js)", "documents": {
        d: {"pdf": pdf, "source_sha256": _file_sha256(d), "pdf_sha256": _file_sha256(pdf),
            "bytes": os.path.getsize(_p(pdf))}
        for d, pdf in sources.items()}}
    with open(_p(PDF_MANIFEST), "w", encoding="utf-8", newline="\n") as f:
        json.dump(man, f, indent=1, sort_keys=True)
        f.write("\n")


def screenshots():
    from PIL import Image
    node = shutil.which("node")
    if not node:
        raise RuntimeError("node not found: screenshots need node and Playwright")
    with tempfile.TemporaryDirectory() as tmp:
        png = os.path.join(tmp, "annotated.png")
        subprocess.run([node, _p("engine", "docs_screenshots.js"), _p(IMG_SOURCE), png], check=True, timeout=300)
        im = Image.open(png).convert("RGB")
        w = 1000
        im = im.resize((w, round(im.size[1] * w / im.size[0])), Image.LANCZOS)
        os.makedirs(_p("docs", "img"), exist_ok=True)
        for q in (80, 72, 64):
            im.save(_p(IMG), quality=q, optimize=True, progressive=True)
            if os.path.getsize(_p(IMG)) <= IMG_LIMIT:
                break
    man = {"image": IMG, "source": IMG_SOURCE,
           "source_sha256": hashlib.sha256(open(_p(IMG_SOURCE), "rb").read()).hexdigest(),
           "image_sha256": hashlib.sha256(open(_p(IMG), "rb").read()).hexdigest(),
           "bytes": os.path.getsize(_p(IMG)), "made_by": "engine/build_docs.py --screenshots (engine/docs_screenshots.js)"}
    with open(_p(IMG_MANIFEST), "w", encoding="utf-8", newline="\n") as f:
        json.dump(man, f, indent=1, sort_keys=True)
        f.write("\n")


def main(argv):
    if argv[:1] == ["--record-suite"]:
        record_suite(*argv[1:6])       # LOG KEY COMMIT COMMAND WHERE
        print("recorded", argv[2], "in", SUITE_RUNS)
        return 0
    if "--screenshots" in argv:
        screenshots()
    facts = all_facts()
    rendered = render(facts)
    if "--check" in argv:
        probs = doc_problems(rendered)
        for p in probs:
            print("DOC", p)
        print(f"doc problems: {len(probs)}")
        return 1 if probs else 0
    for dst, text in rendered.items():
        os.makedirs(os.path.dirname(_p(dst)) or ROOT, exist_ok=True)
        with open(_p(dst), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print("wrote", dst, f"({text.count(chr(10)) + 1} lines)")
    if "--pdfs" in argv:                  # after the documents are written: the PDFs are made from them
        pdfs("--force" in argv)
        print("wrote the PDFs in", PDF_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
