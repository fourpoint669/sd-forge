"""Release gate for explorer pages, and checks that a shipped page still matches its released project.

Standard library only, except that the delay-audit comparison imports engine/delay_audit.py when the project has a
delay_audit.json. Imported by build_explorer.py (before anything is built) and by check_repo.py.

  check_release(dir)   raises Refused unless validation_report.md says 'Overall: **PASS**', validation_results.json
                       has all_pass = true and records the sha256 of the model .mdl and .py and of validation.toml it
                       validated, each equal to the file now on disk, and, where the project has checks.py,
                       checks_results.json has all_pass = true and records the sha256 of every file the checks read
                       (checks.py, the spec, the model, and any other project's files), each equal to the file now.
  model_hash_problems(dir)   the validation-hash part of that check alone.
  output_problems(dir) every result file a page embeds equals the file its generator wrote: validate.py's results
                       (expected set derived from the spec), gate8_analysis.py's outputs and inputs where the project
                       has one, and delay_audit.json against a fresh audit of the current model.
  project_problems(dir)   all of the above for one project, page or not (check_repo.py runs it on every project).
  release_stamp(dir)   check_release, then sha256 of every project file the page rests on (stamp_files: the
                       validation spec, report and results, project checks and their results, the model, and every
                       file the build embeds or reads: bands, loop analysis, delay audit, register, summary, page
                       settings) and of the page template. Embedded in the page (sd-data "release") and in
                       explorer_parity.json. The build computes it after writing explorer.toml, so it covers that too.
  shipped_errors(dir)  for a project that ships explorer.html: the release gate passes now, the page and its parity
                       record carry the same stamp, every stamped file is unchanged since the build, the parity and
                       link/loop-score gates passed, the page is the one recorded (sha256), it has no external
                       references and is under 3 MB. Returns a list of problems (empty = fine).

Limit: the hashes say which files validate.py and checks.py read; they do not re-run validation or the checks. A
results file edited by hand to carry matching hashes would pass (git history is the record against that).
"""
import glob
import hashlib
import json
import os
import re
import sys
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_mode  # noqa: E402
import sd_paths  # noqa: E402
REPO = os.path.dirname(HERE)
# every project file the build reads; the stamp covers the ones that exist (model/*.mdl and model/*.py are added)
STAMPED = ("validation.toml", "validation_report.md", "validation_results.json", "checks.py", "checks_results.json",
           "assumptions_register.md", "summary.md", "mc_bands.csv", "scenario_bands.csv", "loop_dominance.json",
           "gate8_results.json", "delay_audit.json", "explorer.toml", "explorer_glossary.toml", "explorer_intake.toml")
TEMPLATE = os.path.join(HERE, "explorer_template")
SIZE_TARGET = 3 * 1024 * 1024
TOL = 1e-9
EXTERNAL = re.compile(r"""(?:\b(?:src|href|action|poster|data)\s*=\s*["']?\s*(?:https?:)?//)|@import|"""
                      r"""url\(\s*["']?(?:https?:)?//|<link\b""", re.I)


# What the gates protect against (rendered into docs/MANUAL.md by engine/build_docs.py). Each row names the check
# that does it; tests in engine/tests/test_review_findings*.py exercise each one with empty, truncated and changed input.
PROTECTIONS = [
    ("Staleness: the spec, model, project checks code or another project's files changed after validation or checks",
     "sha256 recorded by validate.py, checks.py and gate8_analysis.py compared with the files now "
     "(model_hash_problems, checks_problems, output_problems)"),
    ("Staleness: a result file (bands, policy results, loop dominance, scenario bands) changed after it was written",
     "sha256 recorded by its generator right after writing it (output_problems); delay_audit.json recomputed"),
    ("Staleness: a page built before its project, template or settings changed",
     "release stamp of every project file the page rests on, and the template hash (shipped_errors)"),
    ("Truncation: a simulation that returned fewer time points or columns than the model and spec require",
     "validate.frame_problem in T3, Monte Carlo, the parity gate and the loop-score gate"),
    ("Truncation: fewer runs, results or comparisons than requested",
     "count checks in run_batch, T3, the parity gate, the loop-score gate and the project checks"),
    ("Missing, empty, unparseable or truncated records",
     "required records and their required entries derived from the spec, checks.py and generator declarations "
     "(release_problems, required_external_inputs, generator_declaration)"),
    ("An interrupted or invalid-argument validation run leaving an earlier passing record",
     "the earlier record still describes the unchanged files; any change to them is refused by the hash checks "
     "(tested in test_review_findings3.py::test_f1_*)"),
]
NOT_PROTECTED = [
    "Deliberate editing of evidence files: a record edited by hand to carry hashes that match edited files passes "
    "every gate. The gates detect accidents, not forgery; git history is the record against that.",
    "Errors in the model itself that validation does not test for (validation's own tests are the limit).",
]


class Refused(Exception):
    """The project is not released for an explorer (validation or project checks did not pass)."""


def model_hash_problems(project_dir):
    """The model .mdl and .py named in validation.toml, and validation.toml itself, must be the files validate.py
    hashed in validation_results.json."""
    try:
        m = tomllib.load(open(os.path.join(project_dir, "validation.toml"), "rb"))["model"]
        want = [m["mdl"].replace(os.sep, "/"), m["py"].replace(os.sep, "/")]
    except (OSError, ValueError, KeyError) as e:
        return [f"validation.toml unreadable or without [model] mdl/py ({type(e).__name__})"]
    try:
        res = json.load(open(os.path.join(project_dir, "validation_results.json")))
    except (OSError, ValueError):
        return []          # reported by check_release as missing/unreadable
    out = []
    spec = res.get("spec_files")
    if not isinstance(spec, dict) or "validation.toml" not in spec:
        out.append("validation_results.json does not record the sha256 of validation.toml (re-run engine/validate.py)")
    elif _sha(os.path.join(project_dir, "validation.toml")) != spec["validation.toml"]:
        out.append("validation.toml changed after validation (sha256 differs from validation_results.json): "
                   "re-run engine/validate.py")
    rec = res.get("model_files")
    if not isinstance(rec, dict) or not rec:
        return out + ["validation_results.json does not record the sha256 of the model files it validated "
                      "(re-run engine/validate.py)"]
    for rel in want:
        p = os.path.join(project_dir, rel)
        if rel not in rec:
            out.append(f"validation_results.json has no sha256 for {rel} (re-run engine/validate.py)")
        elif not os.path.exists(p):
            out.append(f"{rel} is missing")
        elif _sha(p) != rec[rel]:
            out.append(f"{rel} changed after validation (sha256 differs from validation_results.json): "
                       "re-run engine/validate.py")
    return out


def check_release(project_dir):
    reasons = release_problems(project_dir)
    if reasons:
        raise Refused("explorer withheld: " + "; ".join(reasons))


def release_problems(project_dir):
    """Every reason the project is not released (empty list = released). Records that are missing, empty,
    unparseable or truncated are reasons, never skipped."""
    reasons = []
    rep = os.path.join(project_dir, "validation_report.md")
    if not os.path.exists(rep) or "Overall: **PASS**" not in open(rep, encoding="utf-8").read():
        reasons.append("validation_report.md does not say 'Overall: **PASS**'")
    try:
        if json.load(open(os.path.join(project_dir, "validation_results.json"))).get("all_pass") is not True:
            reasons.append("validation_results.json: all_pass is not true")
    except (OSError, ValueError):
        reasons.append("validation_results.json missing or unreadable (all_pass unknown)")
    reasons += model_hash_problems(project_dir)
    reasons += checks_problems(project_dir)
    reasons += output_problems(project_dir)
    return reasons


def checks_problems(project_dir):
    """Where the project has checks.py: checks_results.json passes and was produced from the current checks code, spec
    and model, and from the current files of any other project the checks read."""
    if not os.path.exists(os.path.join(project_dir, "checks.py")):
        return []
    try:
        res = json.load(open(os.path.join(project_dir, "checks_results.json")))
    except (OSError, ValueError):
        return ["checks.py exists but checks_results.json is missing or unreadable"]
    out = [] if res.get("all_pass") is True else ["checks_results.json: all_pass is not true"]
    name = os.path.basename(os.path.normpath(project_dir))
    run = "re-run " + name + "/checks.py"
    own, other = res.get("inputs"), res.get("external_inputs")
    try:
        m = tomllib.load(open(os.path.join(project_dir, "validation.toml"), "rb"))["model"]
        need = {"checks.py", "validation.toml", m["mdl"].replace(os.sep, "/"), m["py"].replace(os.sep, "/")}
    except (OSError, ValueError, KeyError):
        need = {"checks.py", "validation.toml"}
    if not isinstance(own, dict) or not need <= set(own) or not isinstance(other, dict):
        return out + [f"checks_results.json does not record the sha256 of the files it checked ({run})"]
    # every other project named in checks.py is a dependency: its spec and model must each be recorded
    for rel in sorted(required_external_inputs(project_dir) - set(other)):
        out.append(f"checks_results.json has no sha256 for {rel} ({run})")
    for base, rec in ((project_dir, own), (None, other)):
        for rel, sha in sorted(rec.items()):
            p = os.path.join(base, rel) if base else external_path(rel)
            if not os.path.exists(p) or _sha(p) != sha:
                out.append(f"{rel} changed after the project checks ran (sha256 differs from checks_results.json): {run}")
    return out


def external_path(rel):
    """A file of another project, as recorded by a project's checks (key 'projects/<name>/<file>', which names the
    project in the projects root; see engine/sd_paths.py). Other keys are relative to the repository."""
    head = "projects/"
    if rel.startswith(head):
        return os.path.join(sd_paths.projects_root(), rel[len(head):])
    return os.path.join(REPO, rel)


def required_external_inputs(project_dir):
    """Files of other projects the checks depend on, derived from checks.py (the other project folders it names) and
    each named project's validation.toml (its spec and model files), never from checks_results.json."""
    name = os.path.basename(os.path.normpath(project_dir))
    src = open(os.path.join(project_dir, "checks.py"), encoding="utf-8").read()
    out = set()
    for other in sorted(_project_names() - {name}):
        if re.search(r"\b" + re.escape(other) + r"\b", src):
            base = f"projects/{other}/"
            out.add(base + "validation.toml")
            try:
                m = tomllib.load(open(external_path(base + "validation.toml"), "rb"))["model"]
                out |= {base + m["mdl"], base + m["py"]}
            except (OSError, ValueError, KeyError):
                pass                       # the missing spec then fails as a missing recorded file
    return out


def generator_declaration(script):
    """(WRITES, READS) as declared at module level in a generator script, read without running it."""
    import ast
    vals = {}
    for node in ast.parse(open(script, encoding="utf-8").read()).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id in ("WRITES", "READS"):
                vals[node.targets[0].id] = set(ast.literal_eval(node.value))
    if set(vals) != {"WRITES", "READS"} or not vals["WRITES"]:
        raise ValueError(f"{os.path.basename(script)} does not declare WRITES and READS")
    return vals["WRITES"], vals["READS"]


def _project_names():
    root = sd_paths.projects_root()
    return {n for n in os.listdir(root) if os.path.isdir(os.path.join(root, n))} if os.path.isdir(root) else set()


def _spec(project_dir):
    try:
        return tomllib.load(open(os.path.join(project_dir, "validation.toml"), "rb"))
    except (OSError, ValueError):
        return None


def expected_validation_outputs(spec):
    """The result files validate.py writes on a passing run, derived from the spec: bands always, policy results when
    it declares [[policies]], loop dominance when it declares [[loops]]."""
    out = {"mc_bands.csv"}
    if spec.get("policies"):
        out.add("policy_results.csv")
    if spec.get("loops"):
        out.add("loop_dominance.json")
    return out


GENERATORS = {"gate8_results.json": "gate8_analysis.py"}       # record written by a project script -> the script


def _script_reads(path):
    """Project files a generator script opens for reading, found in its source (open(os.path.join(HERE, "x")))."""
    src = open(path, encoding="utf-8").read()
    return set(re.findall(r'open\(os\.path\.join\(HERE, "([^"]+)"\)\)', src))


def output_problems(project_dir):
    out = []
    spec = _spec(project_dir)
    try:
        res = json.load(open(os.path.join(project_dir, "validation_results.json")))
    except (OSError, ValueError):
        return out
    if spec is None or res.get("all_pass") is not True:
        return out
    rec = res.get("output_files")
    if not isinstance(rec, dict):
        out.append("validation_results.json does not record the sha256 of the result files it wrote "
                   "(re-run engine/validate.py)")
    else:
        for f in sorted(expected_validation_outputs(spec)):
            p = os.path.join(project_dir, f)
            if f not in rec:
                out.append(f"validation_results.json does not record the sha256 of {f} (re-run engine/validate.py)")
            elif not os.path.exists(p) or _sha(p) != rec[f]:
                out.append(f"{f} changed after validation (sha256 differs from validation_results.json): "
                           "re-run engine/validate.py")
    for record, script in GENERATORS.items():
        rpath, spath = os.path.join(project_dir, record), os.path.join(project_dir, script)
        if not os.path.exists(spath):
            if os.path.exists(rpath):
                out.append(f"{record} exists but its generator {script} does not")
            continue
        run = "re-run " + os.path.basename(os.path.normpath(project_dir)) + "/" + script
        try:
            writes, reads = generator_declaration(spath)
        except (OSError, ValueError, SyntaxError) as e:
            out.append(f"{script}: {e}")
            continue
        try:
            g = json.load(open(rpath))
        except OSError:
            out.append(f"{record} is missing ({run})")
            continue
        except ValueError:
            out.append(f"{record} is empty or unreadable ({run})")
            continue
        outs = g.get("output_files") if isinstance(g, dict) else None
        ins = g.get("inputs") if isinstance(g, dict) else None
        m = spec["model"]
        need = {"output": set(writes), "input": set(reads) | {script, "validation.toml", m["mdl"], m["py"]}}
        for kind, recd in (("output", outs), ("input", ins)):
            if not isinstance(recd, dict):
                out.append(f"{record} does not record the sha256 of the files {script} {'wrote' if kind == 'output' else 'read'} ({run})")
                continue
            for f in sorted(need[kind] - set(recd)):
                out.append(f"{record} does not record the sha256 of {f} ({run})")
            for f, sha in sorted(recd.items()):
                p = os.path.join(project_dir, f)
                if not os.path.exists(p) or _sha(p) != sha:
                    out.append(f"{f} changed after {script} ran (sha256 differs from {record}): {run}")
    if os.path.exists(os.path.join(project_dir, "delay_audit.json")):
        out += delay_audit_problems(project_dir)
    else:
        out.append("delay_audit.json is missing (run engine/delay_audit.py on the project)")
    return out


def delay_audit_problems(project_dir):
    """delay_audit.json must equal a fresh audit of the current model (it is derived, so it is recomputed, not hashed)."""
    import sys
    sys.path.insert(0, HERE)
    import delay_audit
    try:
        fresh = json.loads(json.dumps(delay_audit.audit(project_dir), sort_keys=True))
        if json.load(open(os.path.join(project_dir, "delay_audit.json"))) != fresh:
            return ["delay_audit.json does not match the delay audit of the current model "
                    "(re-run engine/delay_audit.py)"]
    except Exception as e:  # noqa: BLE001 - any failure to reproduce the audit refuses
        return [f"delay_audit.json could not be checked ({type(e).__name__}: {e})"]
    return []


def project_problems(project_dir):
    """Every release-gate problem of one project, whether or not it ships a page (check_repo.py, every project)."""
    return release_problems(project_dir)


def _sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def release_files(project_dir):
    """Project-relative paths of every project file the page rests on (those of STAMPED that exist, and the model)."""
    names = [n for n in STAMPED if os.path.exists(os.path.join(project_dir, n))]
    # plus every project file a generator record names (validate.py's result files, gate8_analysis.py's reads and writes)
    extra = set()
    for rec, keys in (("validation_results.json", ("output_files",)), ("gate8_results.json", ("output_files", "inputs"))):
        if not os.path.exists(os.path.join(project_dir, rec)):
            continue                       # whether it is required is the release gate's question
        r = json.load(open(os.path.join(project_dir, rec)))      # unreadable -> ValueError: the caller reports it
        extra |= {f for k in keys for f in (r.get(k) or {}) if os.path.exists(os.path.join(project_dir, f))}
    names += sorted(f for f in extra - set(names) if not f.startswith("model/"))
    model = sorted(os.path.relpath(p, project_dir).replace(os.sep, "/")
                   for p in glob.glob(os.path.join(glob.escape(project_dir), "model", "*.mdl")) + glob.glob(os.path.join(glob.escape(project_dir), "model", "*.py")))
    return names + model


def template_sha256():
    h = hashlib.sha256()
    for name in sorted(os.listdir(TEMPLATE)):
        p = os.path.join(TEMPLATE, name)
        if os.path.isfile(p):
            h.update(name.encode() + b"\0")
            with open(p, "rb") as f:
                h.update(f.read())
            h.update(b"\0")
    return h.hexdigest()


def release_stamp(project_dir):
    check_release(project_dir)
    checks = os.path.exists(os.path.join(project_dir, "checks.py"))
    return {"gate": "validation_report.md Overall PASS; validation_results.json all_pass, spec and model unchanged since "
                    "validation" + ("; checks_results.json all_pass, checks code, spec and model unchanged since the "
                                    "checks ran" if checks else ""),
            "files": {rel: _sha(os.path.join(project_dir, rel)) for rel in release_files(project_dir)},
            "template_sha256": template_sha256()}


def page_data(html):
    m = re.search(r'<script id="sd-data" type="application/json">(.*?)</script>', html, re.S)
    if not m:
        raise ValueError("no sd-data block")
    return json.loads(m.group(1))


def shipped_errors(project_dir):
    name = os.path.basename(os.path.normpath(project_dir))
    page = os.path.join(project_dir, "explorer.html")
    rec = os.path.join(project_dir, "explorer_parity.json")
    if not os.path.exists(page):
        return [f"{name}: explorer_parity.json without explorer.html"] if os.path.exists(rec) else []
    errs = []
    try:
        errs += [f"{name}: {e}" for e in run_mode.page_problems(project_dir, page_data(open(page, encoding='utf-8').read()), open(page, encoding='utf-8').read())]
    except ValueError:
        pass                                   # unreadable page data is reported below
    try:
        check_release(project_dir)
    except Refused as e:
        errs.append(f"{name}: explorer.html ships but the project is not released ({e})")
    try:
        parity = json.load(open(rec))
    except (OSError, ValueError):
        return errs + [f"{name}: explorer.html ships without a readable explorer_parity.json"]
    raw = open(page, "rb").read()
    html = raw.decode("utf-8")
    if parity.get("html_sha256") != hashlib.sha256(raw).hexdigest():
        errs.append(f"{name}: explorer.html is not the page recorded in explorer_parity.json (rebuild it)")
    if not parity.get("pass") or not (parity.get("max_scale_rel", 1) <= TOL and parity.get("max_pointwise_rel", 1) <= TOL
                                      and parity.get("headline", {}).get("max_rel", 1) <= TOL):
        errs.append(f"{name}: parity gate not passed within {TOL}")
    ltm = parity.get("ltm") or {}
    if ltm.get("mode") not in ("live", "precomputed") or (ltm.get("mode") == "live" and not ltm.get("pass")):
        errs.append(f"{name}: link/loop-score gate result missing or inconsistent")
    stamp = parity.get("release")
    if not stamp:
        errs.append(f"{name}: explorer_parity.json has no release stamp (built before the stamp existed: rebuild)")
    else:
        try:
            if page_data(html).get("release") != stamp:
                errs.append(f"{name}: the page's release stamp differs from explorer_parity.json")
        except ValueError as e:
            errs.append(f"{name}: page data unreadable ({e})")
        try:
            want = set(release_files(project_dir))
        except ValueError as e:
            errs.append(f"{name}: a record the stamp lists files from is unreadable ({e})")
            want = set()
        if set(stamp.get("files", {})) != want:
            errs.append(f"{name}: release files changed: stamped {sorted(stamp.get('files', {}))}, now {sorted(want)}")
        for rel, sha in sorted(stamp.get("files", {}).items()):
            p = os.path.join(project_dir, rel)
            if not os.path.exists(p) or _sha(p) != sha:
                errs.append(f"{name}: {rel} changed since the page was built (rebuild after validation)")
        if stamp.get("template_sha256") != template_sha256():
            errs.append(f"{name}: engine/explorer_template changed since the page was built (rebuild)")
    refs = sorted({m.group(0) for m in EXTERNAL.finditer(html)})
    if refs:
        errs.append(f"{name}: external references in explorer.html: {refs}")
    if len(raw) >= SIZE_TARGET:
        errs.append(f"{name}: explorer.html is {len(raw)} bytes (limit {SIZE_TARGET})")
    return errs
