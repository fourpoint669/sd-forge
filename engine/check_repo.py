"""Repo integrity + licence gate. Exit non-zero on any violation.

Usage:  python -I engine/check_repo.py
Checks: (1) every file under raw/ (except _private/) has a MANIFEST row and every
non-pointer row resolves to a file; (2) nothing under raw/ has commercial_use in
{no, unclear}; (3) raw/_private is not tracked by git; (4) every model in raw/ has
a translation_report row; (5) the git remote is a repository named sd-forge, whoever owns it (checks (3) and (5) apply only when this folder is itself a
git checkout; an unpacked zip has no remote to check); (6) every projects/<model>/ (built by the
/sd-model skill) has its gate files, a passing validation_results.json, a "Model limits" section in summary.md,
no `no`/`unclear` MANIFEST source used as a building block, and any share-alike source flagged in summary.md;
(7) every projects/<model>/explorer.html (built by /sd-explorer, gate 10 of /sd-model) comes from a project that
passes the explorer release gate and still matches it: release stamp equal to the current validation, model and
checks files and page template, parity and link/loop-score gates passed, page = recorded page, no external
references, under 3 MB (engine/explorer_release.py). With --require-explorer, every project must ship one;
(8) every project, with or without a page: the spec, model, result files, project-check inputs and generator
records equal the files their producers hashed (explorer_release.project_problems);
(9) every project built in checkpoint or express mode (engine/run_mode.py) records the mode and its approvals in each gate
file, tags estimated parameters [assumed], opens summary.md with the not-reviewed line, and an express page shows it.
The projects checked are those under the projects root (engine/sd_paths.py): --projects-root DIR, else env
SD_PROJECTS_DIR, else the current directory; inside the engine home itself that default is projects/. When the root is
only the current-directory default, a subfolder counts as a project if it holds validation.toml or 01_problem.md, so
unrelated folders are not flagged; for any other root every subfolder is a project. Checks (1)-(5) always run on the
engine home, from whichever folder this is started.
"""
import glob
import json
import re
import csv
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import explorer_release  # noqa: E402
import run_mode  # noqa: E402
import sd_paths  # noqa: E402

try:
    ARGS, _flag = sd_paths.extract_flag(sys.argv[1:])        # a relative DIR is made absolute before the chdir below
except sd_paths.PathError as _e:
    sys.exit(f"ERROR: {_e}")
REQUIRE_EXPLORER = "--require-explorer" in ARGS
PROJECTS_ROOT, ROOT_SOURCE = sd_paths.projects_root_source()
_root_problem = sd_paths.root_problem(PROJECTS_ROOT, ROOT_SOURCE)
if _root_problem:                                            # an explicit root that is not there would check nothing and pass
    print(f"ERR {_root_problem}")
    sys.exit(1)
sd_paths.set_override(PROJECTS_ROOT)         # fixed now: the chdir below must not change where other projects are looked up

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(root)
errs = []
rows = list(csv.DictReader(open("MANIFEST.csv")))
paths = {r["path"] for r in rows}
disk = set()
priv = os.path.join("raw", "_private")              # that directory and below; raw/_private-wip is NOT exempt
for dp, dn, fn in os.walk("raw"):
    if dp == priv or dp.startswith(priv + os.sep):
        continue
    for f in fn:
        if not f.startswith("."):
            disk.add(os.path.join(dp, f).replace(os.sep, "/"))     # MANIFEST.csv paths use "/" on every platform
errs += [f"on disk, not in MANIFEST: {p}" for p in sorted(disk - paths)]
errs += [f"in MANIFEST, missing on disk: {p}" for p in sorted(p for p in paths - disk if not p.startswith("pointer:"))]
for r in rows:
    if r["path"].startswith("raw/") and r["commercial_use"] not in ("yes", "share-alike"):
        errs.append(f"unlicensed file under raw/: {r['path']} ({r['commercial_use']})")
    if r["commercial_use"] not in ("yes", "no", "share-alike", "unclear"):
        errs.append(f"bad commercial_use: {r['path']}")
    if not r["quality_tier"] in ("A", "B", "C"):
        errs.append(f"bad tier: {r['path']}")
def _git(*args):
    """(return code, stdout, stderr) of a git command; a git that cannot be started is a failure (127), never an exception."""
    try:
        p = subprocess.run(["git", *args], capture_output=True, text=True)
    except OSError as e:
        return 127, "", f"git could not be started ({e})"
    return p.returncode, p.stdout, p.stderr.strip()


# A folder with repository metadata (.git: folder, file or even a dangling link) is a clone and gets every git check; git must
# then work, or that is an error. Only a folder with no .git at all (an unpacked zip, or a folder inside some other
# repository) skips them, and no git process is started for it. Looking at .git can itself fail: that is an error, not "absent".
try:
    GIT_CHECKOUT = sd_paths.git_entry_present(root)
except OSError as _e:
    GIT_CHECKOUT = True
    errs.append(f"cannot look at .git in {root} ({_e}): the git checks cannot be skipped")
GIT_OK = False
if GIT_CHECKOUT:
    _rc, _top, _err = _git("rev-parse", "--show-toplevel")
    if _rc != 0:
        errs.append(f"{root} has a .git but git cannot read the repository ({_err or 'git failed'}); git is needed to check a clone")
    elif os.path.realpath(_top.strip()) != os.path.realpath(root):
        errs.append(f"git reports the top of the repository as {_top.strip()}, not {root}")
    else:
        GIT_OK = True
if GIT_OK:
    _rc, _out, _err = _git("ls-files", "raw/_private")
    if _rc != 0:
        errs.append(f"git ls-files failed ({_err})")
    errs += [f"tracked private file: {t}" for t in _out.split()]
rep = {r["model_path"] for r in csv.DictReader(open("engine/translation_report.csv"))}
models = {p for p in disk if p.lower().endswith((".mdl", ".xmile", ".stmx", ".itmx"))}
errs += [f"no translation status: {p}" for p in sorted(models - rep)]
PROJECT_FILES = ["01_problem.md", "02_boundary.md", "03_dynamic_hypothesis.md", "04_stock_flow.md",
                 "assumptions_register.md", "validation.toml", "validation_report.md", "validation_results.json",
                 "08_policy.md", "summary.md", "sources.md"]
status = {r["path"]: r["commercial_use"] for r in rows}
# listed with os.listdir, not glob: glob reads [ ] * ? in the folder's own name as a pattern and hides read errors
try:
    _names = sorted(os.listdir(PROJECTS_ROOT))
except OSError as _e:
    errs.append(f"cannot read the projects root {PROJECTS_ROOT} ({_e})")
    _names = []
projects = [os.path.join(PROJECTS_ROOT, n, "") for n in _names
            if not n.startswith(".") and os.path.isdir(os.path.join(PROJECTS_ROOT, n))]
if ROOT_SOURCE == "cwd":
    projects = [d for d in projects if os.path.exists(os.path.join(d, "validation.toml"))
                or os.path.exists(os.path.join(d, "01_problem.md"))]
for d in projects:
    errs += [f"{d}: missing {f}" for f in PROJECT_FILES if not os.path.exists(os.path.join(d, f))]
    if not glob.glob(os.path.join(glob.escape(d), "model", "*.mdl")) or not glob.glob(os.path.join(glob.escape(d), "model", "*.py")):
        errs.append(f"{d}: model/ needs the .mdl and its PySD .py")
    try:
        if not json.load(open(os.path.join(d, "validation_results.json"))).get("all_pass"):
            errs.append(f"{d}: validation_results.json is not all_pass")
    except OSError:
        pass                                   # reported above as a missing project file
    except ValueError:
        errs.append(f"{d}: validation_results.json is empty or unreadable")
    if os.path.exists(os.path.join(d, "validation_results.json")):
        # validation hashes, result files, project checks and generator records: every project, page or not
        errs += [f"{d}: {e}" for e in explorer_release.project_problems(d)]
    errs += [f"{d}: {e}" for e in run_mode.project_problems(d)]
    summ = open(os.path.join(d, "summary.md")).read() if os.path.exists(os.path.join(d, "summary.md")) else ""
    if summ and not re.search(r"^#+\s*Model limits", summ, re.M | re.I):
        errs.append(f"{d}: summary.md has no 'Model limits' section")
    src = open(os.path.join(d, "sources.md")).read() if os.path.exists(os.path.join(d, "sources.md")) else ""
    blocks = re.search(r"^## Building blocks.*?(?=^## |\Z)", src, re.M | re.S)
    used = set(re.findall(r"`(raw/[^`]+|pointer:[^`]+)`", blocks.group(0))) if blocks else set()
    for u in sorted(used):
        cu = status.get(u) or next((v for k, v in status.items() if k.startswith(u.rstrip("/") + "/")), None)
        if cu in ("no", "unclear"):
            errs.append(f"{d}: building block {u} has commercial_use={cu} (pointer-only)")
        if cu == "share-alike" and "share-alike" not in summ.lower():
            errs.append(f"{d}: reuses share-alike {u} but summary.md does not flag it")
explorers = 0
for d in projects:
    errs += explorer_release.shipped_errors(d)
    if os.path.exists(os.path.join(d, "explorer.html")):
        explorers += 1
    elif REQUIRE_EXPLORER:
        errs.append(f"{d}: no explorer.html (run /sd-explorer, gate 10)")
if GIT_OK:
    _rc, remote, _err = _git("remote", "get-url", "origin")
    remote = remote.strip()
    if _rc != 0:
        errs.append(f"git could not read the remote ({_err}); a clone needs a remote named origin that points at a repository called sd-forge")
    elif not re.search(r"(?:^|[/:])sd-forge(?:\.git)?/?$", remote):          # the owner can be renamed; the repository name is the identity
        errs.append(f"unexpected remote: {remote}")
elif not GIT_CHECKOUT:
    print("NOTE: this folder is not a git checkout (an unpacked zip?): the git remote and private-file checks were skipped.",
          file=sys.stderr)
print(f"rows={len(rows)} raw_files={len(disk)} models={len(models)} projects={len(projects)} explorers={explorers} "
      f"errors={len(errs)}")
for e in errs[:50]:
    print("ERR", e)
sys.exit(1 if errs else 0)
