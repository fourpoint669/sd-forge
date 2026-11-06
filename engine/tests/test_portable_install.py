"""Install once, use anywhere (engine/sd_paths.py, install-skills.sh, the skills' path preamble): engine home and projects
root resolution (set, unset, missing config, bad path); the explorer build and check_repo run from a folder outside the
repository on a copy of a validated project and pass every gate; the release gate still refuses a modified model file
when the project is outside the repository; install-skills.sh and uninstall-skills.sh are idempotent and never overwrite
what is not theirs. Path resolution only: no gate, tolerance or threshold is exercised differently here."""
import hashlib
import os
import re
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "engine"))
import sd_paths  # noqa: E402

BASS = os.path.join(ROOT, "projects", "bass-b2b-adoption")
SAAS = os.path.join(ROOT, "projects", "saas-churn-vs-winrate")
INSTALL = os.path.join(ROOT, "install-skills.sh")
INSTALL_DIR = ROOT
UNINSTALL = os.path.join(ROOT, "uninstall-skills.sh")
SKILLS = {n: os.path.join(ROOT, ".claude", "skills", n, "SKILL.md") for n in ("sd-model", "sd-explorer")}
COMMANDS = {n: os.path.join(ROOT, ".claude", "commands", n + ".md") for n in ("sd-model", "sd-explorer")}
PAGE_FILES = ("explorer.html", "explorer_parity.json")


def _fake_home(tmp_path, name="home"):
    """A folder that passes the engine-home check."""
    h = tmp_path / name
    (h / "engine").mkdir(parents=True)
    (h / "engine" / "validate.py").write_text("")
    return h


posix_only = pytest.mark.skipif(sys.platform == "win32", reason="the installer and setup.command are bash scripts and "
                                "the skills call .venv/bin/python: Windows is not supported (docs/QUICKSTART.md, Windows)")


@pytest.fixture(autouse=True)
def _reset_override():
    sd_paths.set_override(None)
    yield
    sd_paths.set_override(None)


# ---- engine home ------------------------------------------------------------------------------------------------------

def test_home_from_environment(tmp_path):
    h = _fake_home(tmp_path)
    assert sd_paths.engine_home(env={"SD_FORGE_HOME": str(h)}, config=str(tmp_path / "none")) == str(h)


def test_home_from_config_when_env_unset(tmp_path):
    h = _fake_home(tmp_path)
    cfg = tmp_path / "config-file"
    cfg.write_text(str(h) + "\nignored second line\n")
    assert sd_paths.engine_home(env={}, config=str(cfg)) == str(h)


def test_environment_wins_over_config(tmp_path):
    a, b = _fake_home(tmp_path, "a"), _fake_home(tmp_path, "b")
    cfg = tmp_path / "cfg"
    cfg.write_text(str(b))
    assert sd_paths.engine_home(env={"SD_FORGE_HOME": str(a)}, config=str(cfg)) == str(a)


def test_missing_config_and_env_fails_with_a_clear_message(tmp_path):
    with pytest.raises(sd_paths.PathError) as e:
        sd_paths.engine_home(env={}, config=str(tmp_path / "absent"))
    msg = str(e.value)
    assert "SD_FORGE_HOME" in msg and str(tmp_path / "absent") in msg and "install-skills.sh" in msg


def test_empty_config_fails(tmp_path):
    cfg = tmp_path / "cfg"
    cfg.write_text("\n")
    with pytest.raises(sd_paths.PathError, match="empty"):
        sd_paths.engine_home(env={}, config=str(cfg))


@pytest.mark.parametrize("where", ["env", "config"])
def test_path_without_engine_validate_fails_naming_the_path(tmp_path, where):
    bad = tmp_path / "not-a-home"
    bad.mkdir()
    cfg = tmp_path / "cfg"
    cfg.write_text(str(bad))
    env = {"SD_FORGE_HOME": str(bad)} if where == "env" else {}
    with pytest.raises(sd_paths.PathError) as e:
        sd_paths.engine_home(env=env, config=str(cfg))
    assert str(bad) in str(e.value) and "engine/validate.py" in str(e.value)


def test_config_file_location_is_under_the_user_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))          # Windows reads this one for "~"
    assert sd_paths.config_file() == str(tmp_path / ".config" / "sd-forge" / "home")


# ---- projects root ----------------------------------------------------------------------------------------------------

def test_projects_root_defaults_to_the_current_directory(tmp_path):
    assert sd_paths.projects_root_source(env={}, cwd=str(tmp_path)) == (str(tmp_path), "cwd")


def test_projects_root_env_beats_cwd_and_flag_beats_env(tmp_path):
    e, f = tmp_path / "e", tmp_path / "f"
    assert sd_paths.projects_root_source(env={"SD_PROJECTS_DIR": str(e)}, cwd=str(tmp_path)) == (str(e), "env")
    assert sd_paths.projects_root_source(flag=str(f), env={"SD_PROJECTS_DIR": str(e)}, cwd=str(tmp_path)) == (str(f), "flag")


def test_inside_the_engine_home_the_default_is_its_projects_folder():
    assert sd_paths.projects_root_source(env={}, cwd=ROOT) == (os.path.join(ROOT, "projects"), "home")
    assert sd_paths.projects_root_source(env={}, cwd=os.path.join(ROOT, "engine"))[1] == "cwd"


def test_extract_flag_forms_and_relative_values_become_absolute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert sd_paths.extract_flag(["a", "--projects-root", "rel", "b"]) == (["a", "b"], "rel")
    assert sd_paths.projects_root(env={}) == str(tmp_path / "rel")
    assert sd_paths.extract_flag(["--projects-root=/x/y", "c"]) == (["c"], "/x/y")
    assert sd_paths.projects_root(env={"SD_PROJECTS_DIR": "/ignored"}) == os.path.abspath("/x/y")
    with pytest.raises(sd_paths.PathError):
        sd_paths.extract_flag(["--projects-root"])


def test_resolve_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = str(tmp_path / "root")
    assert sd_paths.resolve_project("projects/x", root) == str(tmp_path / "projects" / "x")      # a path: as given
    assert sd_paths.resolve_project("model-a", root) == os.path.join(root, "model-a")            # a bare name: in the root
    (tmp_path / "model-b").mkdir()
    assert sd_paths.resolve_project("model-b", root) == str(tmp_path / "model-b")                # exists as given


def test_cli_reports_errors_and_values(tmp_path):
    h = _fake_home(tmp_path)
    (h / "engine" / "sd_paths.py").write_text(open(os.path.join(ROOT, "engine", "sd_paths.py")).read())
    env = {"PATH": os.environ["PATH"], "HOME": str(tmp_path / "nohome")}
    p = subprocess.run([sys.executable, "-I", str(h / "engine" / "sd_paths.py"), "home"], env=env, capture_output=True, text=True)
    assert p.returncode == 1 and "install-skills.sh" in p.stderr
    env["SD_FORGE_HOME"] = str(h)
    p = subprocess.run([sys.executable, "-I", str(h / "engine" / "sd_paths.py"), "check", "--projects-root", str(tmp_path)],
                       env=env, capture_output=True, text=True)
    assert p.returncode == 0 and p.stdout.split() == [f"home={h}", f"projects_root={tmp_path}"], p.stdout


# ---- the path preamble in the skills ----------------------------------------------------------------------------------

def _preamble(path):
    m = re.search(r"```bash\n(SD_HOME=.*?)\n```", open(path, encoding="utf-8").read(), re.S)
    assert m, path
    return m.group(1)


def test_both_skills_carry_the_same_preamble_and_commands_point_to_it():
    assert _preamble(SKILLS["sd-model"]) == _preamble(SKILLS["sd-explorer"])
    for c in COMMANDS.values():
        text = open(c, encoding="utf-8").read()
        assert '"Where things are"' in text and "stop with its message if sd-forge is not installed" in text


def test_skills_call_the_engine_by_absolute_path_only():
    for p in SKILLS.values():
        text = open(p, encoding="utf-8").read()
        assert not re.search(r"(?<!SD_HOME/)\.venv/bin/python", text), p
        assert "python -I engine/" not in text, p
        assert not re.search(r"(?<!\$PROJECTS/)projects/<", text), p


def _run_preamble(snippet, env, cwd):
    return subprocess.run(["bash", "-c", snippet], env=env, cwd=cwd, capture_output=True, text=True)


@posix_only
def test_the_preamble_runs_with_env_with_a_config_and_fails_clearly_without_either(tmp_path):
    h = _fake_home(tmp_path)
    shutil.copy(os.path.join(ROOT, "engine", "sd_paths.py"), h / "engine" / "sd_paths.py")
    (h / ".venv" / "bin").mkdir(parents=True)
    os.symlink(sys.executable, h / ".venv" / "bin" / "python")
    work = tmp_path / "work"
    work.mkdir()
    snippet = _preamble(SKILLS["sd-model"])
    base = {"PATH": os.environ["PATH"], "HOME": str(tmp_path / "user")}
    p = _run_preamble(snippet, dict(base, SD_FORGE_HOME=str(h)), work)
    assert p.returncode == 0 and p.stdout.split() == [f"home={h}", f"projects_root={work}"], (p.stdout, p.stderr)
    cfg = tmp_path / "user" / ".config" / "sd-forge" / "home"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(str(h) + "\n")
    p = _run_preamble(snippet, dict(base, SD_PROJECTS_DIR=str(tmp_path / "elsewhere")), work)
    assert p.returncode == 0 and p.stdout.split() == [f"home={h}", f"projects_root={tmp_path / 'elsewhere'}"], (p.stdout, p.stderr)
    cfg.unlink()
    p = _run_preamble(snippet, base, work)
    assert p.returncode == 1 and "install-skills.sh" in p.stderr and "not installed" in p.stderr


# ---- running from outside the repository -------------------------------------------------------------------------------

def _sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def _copy(src, dest_root, keep_page=False):
    d = dest_root / os.path.basename(src)
    shutil.copytree(src, d, ignore=None if keep_page else shutil.ignore_patterns(*PAGE_FILES))
    return d


def _run(script, args, cwd, **env_changes):
    """Run an engine script by absolute path from cwd, with the engine home in the environment and no projects root
    inherited from the suite (conftest pins SD_PROJECTS_DIR for the in-repo tests)."""
    env = {k: v for k, v in os.environ.items() if k != "SD_PROJECTS_DIR"}
    env["SD_FORGE_HOME"] = ROOT
    env.update(env_changes)
    return subprocess.run([sys.executable, "-I", os.path.join(ROOT, "engine", script), *args], cwd=cwd, env=env,
                          capture_output=True, text=True)


def test_explorer_build_from_an_outside_folder_passes_every_gate(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    d = _copy(BASS, work)
    repo_before = {f: _sha(os.path.join(BASS, f)) for f in PAGE_FILES}
    p = _run("build_explorer.py", ["bass-b2b-adoption"], cwd=work)          # a bare name, looked up in the current folder
    assert p.returncode == 0, p.stdout + p.stderr
    for f in PAGE_FILES:
        assert (d / f).exists(), f
        assert not (work / f).exists()
    assert "parity vs PySD" in p.stdout and "external references: none" in p.stdout
    # the build is deterministic and path-independent: the page equals the one built inside the repository
    assert _sha(d / "explorer.html") == repo_before["explorer.html"]
    assert {f: _sha(os.path.join(BASS, f)) for f in PAGE_FILES} == repo_before      # nothing was written into the repo
    chk = _run("check_repo.py", ["--require-explorer"], cwd=work)                    # the root is the current folder
    assert chk.returncode == 0 and "projects=1 explorers=1 errors=0" in chk.stdout, chk.stdout
    assert _run("run_mode.py", ["check", "bass-b2b-adoption"], cwd=work).returncode == 0


def test_the_flag_and_the_environment_name_the_root_from_any_folder(tmp_path):
    root, other = tmp_path / "root", tmp_path / "elsewhere"
    root.mkdir()
    other.mkdir()
    _copy(BASS, root, keep_page=True)
    by_flag = _run("check_repo.py", ["--require-explorer", "--projects-root", str(root)], cwd=other)
    by_env = _run("check_repo.py", ["--require-explorer"], cwd=other, SD_PROJECTS_DIR=str(root))
    rel = _run("check_repo.py", ["--require-explorer", "--projects-root", "../root"], cwd=other)   # relative to the cwd
    for p in (by_flag, by_env, rel):
        assert p.returncode == 0 and "projects=1 explorers=1 errors=0" in p.stdout, p.stdout
    assert "projects=0" in _run("check_repo.py", [], cwd=other).stdout        # the current folder has no projects


def test_the_current_folder_default_ignores_unrelated_folders(tmp_path):
    (tmp_path / "Documents").mkdir()
    (tmp_path / "Documents" / "notes.txt").write_text("x")
    p = _run("check_repo.py", [], cwd=tmp_path)
    assert p.returncode == 0 and "projects=0 explorers=0 errors=0" in p.stdout, p.stdout
    flagged = _run("check_repo.py", ["--projects-root", str(tmp_path)], cwd=tmp_path)   # an explicit root stays strict
    assert flagged.returncode == 1 and "Documents/: missing 01_problem.md" in flagged.stdout.replace("\\", "/"), flagged.stdout


@pytest.mark.parametrize("victim", ["model/bass_b2b_adoption.mdl", "model/bass_b2b_adoption.py", "validation.toml"])
def test_the_release_gate_refuses_a_modified_file_outside_the_repo(tmp_path, victim):
    work = tmp_path / "work"
    work.mkdir()
    d = _copy(BASS, work, keep_page=True)
    assert _run("check_repo.py", ["--require-explorer"], cwd=work).returncode == 0            # baseline: consistent
    with open(d / victim, "a", encoding="utf-8") as f:
        f.write("\n# edited after validation\n" if victim.endswith((".py", ".toml")) else "\n")
    chk = _run("check_repo.py", ["--require-explorer"], cwd=work)
    assert chk.returncode == 1 and "changed after validation" in chk.stdout, chk.stdout
    for f in PAGE_FILES:
        os.remove(d / f)
    b = _run("build_explorer.py", ["bass-b2b-adoption"], cwd=work)
    assert b.returncode == 1 and b.stdout.startswith("REFUSED: explorer withheld:") and "changed after validation" in b.stdout, b.stdout
    assert not any((d / f).exists() for f in PAGE_FILES)                       # nothing written


def test_a_project_depending_on_another_finds_it_in_the_same_root_and_is_refused_without_it(tmp_path):
    both = tmp_path / "both"
    both.mkdir()
    _copy(BASS, both, keep_page=True)
    _copy(SAAS, both, keep_page=True)
    ok = _run("check_repo.py", ["--require-explorer"], cwd=both)
    assert ok.returncode == 0 and "projects=2 explorers=2 errors=0" in ok.stdout, ok.stdout
    with open(both / "bass-b2b-adoption" / "validation.toml", "a", encoding="utf-8") as f:
        f.write("\n# edited\n")
    bad = _run("check_repo.py", ["--require-explorer"], cwd=both)        # saas's checks recorded bass's spec hash
    assert bad.returncode == 1 and "saas-churn-vs-winrate" in bad.stdout and "changed after" in bad.stdout, bad.stdout
    alone = tmp_path / "alone"
    alone.mkdir()
    _copy(SAAS, alone, keep_page=True)
    p = _run("check_repo.py", ["--require-explorer"], cwd=alone)         # no fallback to the engine home's copy
    assert p.returncode == 1 and "projects/bass-b2b-adoption/" in p.stdout, p.stdout


# ---- install-skills.sh / uninstall-skills.sh --------------------------------------------------------------------------

def _sh(script, home, *args, python=False, codex=False, env_extra=None):
    """Run an installer script with a temporary HOME. The Python-environment step is skipped (--no-python) unless
    python=True: it is tested separately, on a copy, because it builds a virtual environment. Codex is left out
    (--no-codex) unless codex=True. codex=True only stops --no-codex being passed, leaving the installer in auto
    mode: a test that must not depend on whether this machine has Codex passes --codex itself."""
    env = {"PATH": os.environ["PATH"], "HOME": str(home), "SD_INSTALL_NO_DIALOG": "1", **(env_extra or {})}
    extra = []
    if os.path.basename(script) == "install-skills.sh":
        extra += [] if python else ["--no-python"]
        extra += [] if codex else ["--no-codex"]
    return subprocess.run(["bash", script, *extra, *args], env=env, capture_output=True, text=True)


def _tree(home):
    """Every link and file the installer may write (pip's own cache under HOME is not its concern)."""
    out = {}
    for sub in (".config", ".claude"):
        out.update(_tree_of(os.path.join(home, sub), home))
    return out


def _tree_of(top, home):
    out = {}
    for dp, dn, fn in os.walk(top):
        for n in dn + fn:
            p = os.path.join(dp, n)
            out[os.path.relpath(p, home)] = os.readlink(p) if os.path.islink(p) else (open(p).read() if os.path.isfile(p) else "")
    return out


LINKS = {".claude/skills/sd-model": ".claude/skills/sd-model", ".claude/skills/sd-explorer": ".claude/skills/sd-explorer",
         ".claude/commands/sd-model.md": ".claude/commands/sd-model.md",
         ".claude/commands/sd-explorer.md": ".claude/commands/sd-explorer.md"}


@posix_only
def test_install_writes_home_and_links_and_is_idempotent(tmp_path):
    first = _sh(INSTALL, tmp_path)
    assert first.returncode == 0, first.stderr
    assert (tmp_path / ".config" / "sd-forge" / "home").read_text() == ROOT + "\n"
    for link, rel in LINKS.items():
        assert os.readlink(tmp_path / link) == os.path.join(ROOT, rel)
        assert os.path.exists(tmp_path / link)                                  # the link resolves
    assert first.stdout.count("linked:") == 4 and "wrote:" in first.stdout
    snapshot = _tree(tmp_path)
    second = _sh(INSTALL, tmp_path)
    assert second.returncode == 0 and _tree(tmp_path) == snapshot
    assert second.stdout.count("unchanged:") == 5 and "linked:" not in second.stdout.replace("already linked", "")
    # what the skills would read through the link is the repository's file
    assert open(tmp_path / ".claude/skills/sd-model/SKILL.md").read() == open(SKILLS["sd-model"]).read()


@posix_only
def test_install_refuses_to_overwrite_a_different_file_and_changes_nothing(tmp_path):
    (tmp_path / ".claude" / "commands").mkdir(parents=True)
    mine = tmp_path / ".claude" / "commands" / "sd-model.md"
    mine.write_text("my own command\n")
    before = _tree(tmp_path)
    p = _sh(INSTALL, tmp_path)
    assert p.returncode == 1 and "REFUSED" in p.stderr and "sd-model.md" in p.stderr and "Nothing was changed" in p.stderr
    assert _tree(tmp_path) == before and mine.read_text() == "my own command\n"
    assert not (tmp_path / ".config").exists()
    forced = _sh(INSTALL, tmp_path, "--force")                                  # --force never replaces a real file
    assert forced.returncode == 1 and mine.read_text() == "my own command\n"


@posix_only
def test_install_refuses_a_link_or_home_pointing_elsewhere_unless_forced(tmp_path):
    (tmp_path / ".claude" / "skills").mkdir(parents=True)
    os.symlink("/somewhere/else", tmp_path / ".claude" / "skills" / "sd-model")
    p = _sh(INSTALL, tmp_path)
    assert p.returncode == 1 and "--force" in p.stderr
    assert os.readlink(tmp_path / ".claude" / "skills" / "sd-model") == "/somewhere/else"
    f = _sh(INSTALL, tmp_path, "--force")
    assert f.returncode == 0 and os.readlink(tmp_path / ".claude" / "skills" / "sd-model") == os.path.join(ROOT, ".claude/skills/sd-model")
    (tmp_path / ".config" / "sd-forge" / "home").write_text("/another/checkout\n")
    g = _sh(INSTALL, tmp_path)
    assert g.returncode == 1 and "different home" in g.stderr and (tmp_path / ".config/sd-forge/home").read_text() == "/another/checkout\n"
    assert _sh(INSTALL, tmp_path, "--force").returncode == 0
    assert (tmp_path / ".config/sd-forge/home").read_text() == ROOT + "\n"


@posix_only
def test_uninstall_removes_only_what_install_made(tmp_path):
    assert _sh(INSTALL, tmp_path).returncode == 0
    foreign = tmp_path / ".claude" / "skills" / "other-skill"
    foreign.mkdir()
    (foreign / "SKILL.md").write_text("x")
    p = _sh(UNINSTALL, tmp_path)
    assert p.returncode == 0 and p.stdout.count("removed:") == 5
    left = _tree(tmp_path)
    assert set(left) >= {".claude/skills/other-skill", ".claude/skills/other-skill/SKILL.md"}
    assert not any(k.startswith((".config/sd-forge",)) for k in left) and not any("sd-model" in k or "sd-explorer" in k for k in left)
    again = _sh(UNINSTALL, tmp_path)
    assert again.returncode == 0 and again.stdout.count("absent:") == 5
    os.symlink("/somewhere/else", tmp_path / ".claude" / "skills" / "sd-model")      # a foreign link with our name stays
    assert "left:" in _sh(UNINSTALL, tmp_path).stdout and os.path.islink(tmp_path / ".claude" / "skills" / "sd-model")


# ---- the installer finds a supported Python and builds the environment ------------------------------------------------

def _mini_repo(tmp_path, name="repo", parent=None):
    """What the installer needs from a checkout: itself, the skills and commands, the requirements and engine/validate.py."""
    d = (parent or tmp_path) / name
    (d / "engine").mkdir(parents=True)
    (d / "engine" / "validate.py").write_text("")
    shutil.copy(os.path.join(ROOT, "engine", "requirements.txt"), d / "engine" / "requirements.txt")
    shutil.copytree(os.path.join(ROOT, ".claude"), d / ".claude")
    ex = d / "projects" / "bass-b2b-adoption"
    ex.mkdir(parents=True)
    for f in ("validation.toml", "mc_bands.csv", "policy_results.csv"):
        shutil.copy(os.path.join(ROOT, "projects", "bass-b2b-adoption", f), ex / f)
    for f in ("install-skills.sh", "uninstall-skills.sh", "setup.command"):
        shutil.copy(os.path.join(ROOT, f), d / f)
    return d


def _tools(tmp_path, fakes):
    """A PATH holding only the utilities the installer needs plus fake interpreters: {name: version it reports}."""
    t = tmp_path / "tools"
    t.mkdir(exist_ok=True)
    for tool in ("dirname", "head", "sed", "awk", "readlink", "ln", "rm", "mkdir", "cat", "grep", "bash", "cp", "sort", "mktemp", "cmp", "mv", "rmdir", "chmod", "touch", "tr", "cut", "ls", "date", "id", "tail", "wc", "find"):
        if not (t / tool).is_symlink():
            os.symlink(shutil.which(tool), t / tool)
    for name, version in fakes.items():
        f = t / name
        f.write_text(f"#!/bin/sh\necho {version}\n")
        f.chmod(0o755)
    return str(t)


def _check_python(repo, path):
    return subprocess.run([shutil.which("bash"), str(repo / "install-skills.sh"), "--check-python"],
                          env={"PATH": path, "HOME": str(repo)}, capture_output=True, text=True)


@posix_only
def test_supported_python_versions_match_the_skill_text():
    versions = re.search(r'^SUPPORTED="([\d. ]+)"', open(INSTALL).read(), re.M).group(1).split()
    said = re.search(r"Python (3\.\d+) or (3\.\d+)", open(SKILLS["sd-model"], encoding="utf-8").read()).groups()
    assert sorted(versions) == sorted(said)


@pytest.mark.parametrize("fakes,want", [
    ({"python3.12": "3.12", "python3.11": "3.11", "python3": "3.14"}, "python3.12"),     # newest supported wins over python3
    ({"python3.11": "3.11", "python3": "3.14"}, "python3.11"),
    ({"python3": "3.12"}, "python3"),                                                    # a plain python3 that is supported
    ({"python3": "3.11", "python": "3.9"}, "python3"),
])
@posix_only
def test_installer_picks_a_supported_python(tmp_path, fakes, want):
    repo = _mini_repo(tmp_path)
    p = _check_python(repo, _tools(tmp_path, fakes))
    assert p.returncode == 0 and p.stdout.split()[0].endswith("/" + want), p.stdout + p.stderr


@posix_only
def test_installer_with_no_python_at_all_says_what_to_install_and_changes_nothing(tmp_path):
    repo = _mini_repo(tmp_path)
    tools = _tools(tmp_path, {})
    p = _check_python(repo, tools)
    assert p.returncode == 1 and "no usable Python found" in p.stderr and "3.12 or 3.11" in p.stderr
    assert "brew install python@3.12" in p.stderr and "python.org" in p.stderr
    full = subprocess.run([shutil.which("bash"), str(repo / "install-skills.sh")], env={"PATH": tools, "HOME": str(tmp_path / "h")},
                          capture_output=True, text=True)
    assert full.returncode == 1 and "Nothing was changed" in full.stderr
    assert not (tmp_path / "h").exists() and not (repo / ".venv").exists()          # nothing linked, nothing half-built


@posix_only
def test_a_python_older_than_the_supported_ones_is_never_considered(tmp_path):
    repo = _mini_repo(tmp_path)
    p = _check_python(repo, _tools(tmp_path, {"python3": "3.9", "python": "3.10"}))
    assert p.returncode == 1 and "no usable Python found" in p.stderr


@pytest.mark.parametrize("fakes,want", [({"python3": "3.14"}, "python3"), ({"python3.14": "3.14", "python3.13": "3.13"}, "python3.13"),
                                         ({"python3": "3.13", "python3.14": "3.14"}, "python3")])
@posix_only
def test_check_python_reports_a_newer_python_as_conditional_and_prefers_the_lowest(tmp_path, fakes, want):
    repo = _mini_repo(tmp_path)
    p = _check_python(repo, _tools(tmp_path, fakes))
    first = p.stdout.split()[0]
    assert p.returncode == 0 and first.endswith("/" + want) and "newer than the supported ones" in p.stdout and "self-check" in p.stdout


FAKE_PYTHON = r"""#!/bin/sh
# a fake newer interpreter and the virtual environment it makes: reports 3.14, "installs" packages, and "validates"
# by copying the result files it was told to produce (FAKE_RESULTS)
case "$*" in
  *"-m venv"*) mkdir -p "$3/bin"; cp "$0" "$3/bin/python"; exit 0 ;;
  *"sys.version_info"*) echo 3.14; exit 0 ;;
  *"-m pip"*) exit 0 ;;
  *"import pysd"*) exit 0 ;;
  *validate.py*) spec=""; for a in "$@"; do spec="$a"; done; cp "$FAKE_RESULTS/mc_bands.csv" "$FAKE_RESULTS/policy_results.csv" "$(dirname "$spec")/"; echo "ALL PASS"; exit 0 ;;
esac
exit 1
"""


def _newer_python_run(tmp_path, results_dir):
    repo = _mini_repo(tmp_path)
    tools = _tools(tmp_path, {})
    fake = os.path.join(tools, "python3.14")
    open(fake, "w").write(FAKE_PYTHON)
    os.chmod(fake, 0o755)
    home = tmp_path / "h"
    env = {"PATH": tools, "HOME": str(home), "SD_INSTALL_NO_DIALOG": "1", "FAKE_RESULTS": str(results_dir)}
    p = subprocess.run([shutil.which("bash"), str(repo / "install-skills.sh"), "--no-codex"], env=env, capture_output=True, text=True)
    return repo, home, p


@posix_only
def test_a_newer_python_that_reproduces_the_example_is_accepted_and_recorded(tmp_path):
    same = tmp_path / "same"
    shutil.copytree(os.path.join(ROOT, "projects", "bass-b2b-adoption"), same)           # the committed result files
    repo, home, p = _newer_python_run(tmp_path, same)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "newer than the ones sd-forge was developed on" in p.stdout and "reproduces the shipped example exactly" in p.stdout
    assert (repo / ".venv" / ".sd-forge-verified").read_text().startswith("python=3.14\n")
    assert os.path.islink(home / ".claude" / "skills" / "sd-model")
    again = subprocess.run([shutil.which("bash"), str(repo / "install-skills.sh"), "--no-codex"], env={
        "PATH": _tools(tmp_path, {}), "HOME": str(home), "SD_INSTALL_NO_DIALOG": "1", "FAKE_RESULTS": str(same)}, capture_output=True, text=True)
    assert again.returncode == 0 and "unchanged: " + str(repo / ".venv") in again.stdout and "Checking that it reproduces" not in again.stdout


@posix_only
def test_a_newer_python_that_does_not_reproduce_the_example_is_refused_and_cleaned_up(tmp_path):
    different = tmp_path / "different"
    different.mkdir()
    for f in ("mc_bands.csv", "policy_results.csv"):
        (different / f).write_text("time,x\n0,1\n")                                    # not what the example produces
    repo, home, p = _newer_python_run(tmp_path, different)
    assert p.returncode == 1 and "did NOT reproduce" in p.stderr and "Nothing was changed" in p.stderr
    assert not (repo / ".venv").exists() and not home.exists()                         # environment deleted, nothing linked


@posix_only
def test_an_existing_environment_of_a_newer_python_is_never_deleted(tmp_path):
    repo = _mini_repo(tmp_path)
    (repo / ".venv" / "bin").mkdir(parents=True)
    fake = repo / ".venv" / "bin" / "python"
    body = '#!/bin/sh\ncase "$*" in *pysd*) exit 1;; esac\necho 3.14\n'              # reports 3.14, cannot import the packages
    fake.write_text(body)
    fake.chmod(0o755)
    p = _sh(str(repo / "install-skills.sh"), tmp_path / "h", python=True)
    assert p.returncode == 1 and "rm -rf" in p.stderr
    assert not (tmp_path / "h").exists() and fake.read_text() == body


def _pypi_reachable():
    import socket
    try:
        socket.create_connection(("pypi.org", 443), timeout=4).close()
        return True
    except OSError:
        return False


@posix_only
def test_a_fresh_unpacked_folder_installs_end_to_end(tmp_path):
    """Like a friend who unpacks the zip and runs the installer: it builds .venv itself, links the skills, prints what
    to type, and a second run changes nothing."""
    which = subprocess.run([shutil.which("bash"), INSTALL, "--check-python"], capture_output=True, text=True)
    if which.returncode != 0:
        pytest.skip("no supported Python on this machine: " + which.stderr.strip()[:80])
    if not _pypi_reachable():
        pytest.skip("pypi.org is not reachable (the installer needs the internet to install the packages)")
    repo = _mini_repo(tmp_path)
    home = tmp_path / "home"
    first = _sh(str(repo / "install-skills.sh"), home, python=True)
    assert first.returncode == 0, first.stdout + first.stderr
    py = repo / ".venv" / "bin" / "python"
    ok = subprocess.run([str(py), "-c", "import pysd, numpy, scipy, pandas, xarray, networkx, matplotlib"], capture_output=True, text=True)
    assert ok.returncode == 0, ok.stderr
    assert first.stdout.count("linked:") == 4 and "created:" in first.stdout
    assert '/sd-model "' in first.stdout and "/sd-explorer" in first.stdout and "sd-forge is installed" in first.stdout
    assert (home / ".config" / "sd-forge" / "home").read_text() == str(repo) + "\n"
    snapshot = _tree(home)
    second = _sh(str(repo / "install-skills.sh"), home, python=True)
    assert second.returncode == 0 and _tree(home) == snapshot
    assert "created:" not in second.stdout and "unchanged: " + str(repo / ".venv") in second.stdout


# ---- an unpacked zip has no git remote to check -------------------------------------------------------------------------

def _repo_copy(tmp_path):
    d = tmp_path / "unzipped"
    shutil.copytree(ROOT, d, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", ".pytest_cache"))
    return d


@posix_only
def test_check_repo_works_on_an_unpacked_zip_and_still_checks_a_clone(tmp_path):
    d = _repo_copy(tmp_path)

    def run():
        env = {k: v for k, v in os.environ.items() if k != "SD_PROJECTS_DIR"}
        return subprocess.run([sys.executable, "-I", str(d / "engine" / "check_repo.py"), "--projects-root", str(d / "projects"),
                               "--require-explorer"], cwd=tmp_path, env=env, capture_output=True, text=True)
    zip_like = run()                                                    # no .git at all
    assert zip_like.returncode == 0 and "errors=0" in zip_like.stdout, zip_like.stdout
    assert "not a git checkout" in zip_like.stderr
    git = lambda *a: subprocess.run(["git", *a], cwd=d, capture_output=True, text=True, check=True)   # noqa: E731
    git("init", "-q")
    git("remote", "add", "origin", "https://github.com/someone-else/other.git")
    wrong = run()                                                       # a clone of something else is still refused
    assert wrong.returncode == 1 and "unexpected remote" in wrong.stdout and "not a git checkout" not in wrong.stderr
    for url in ("https://github.com/fourpoint669/sd-forge.git", "https://github.com/anyone-renamed/sd-forge",
                "git@github.com:fourpoint669/sd-forge.git", "https://github.com/anyone/sd-forge.git/"):
        git("remote", "set-url", "origin", url)                        # the owner can change; the repository name is the identity
        right = run()
        assert right.returncode == 0 and "errors=0" in right.stdout, (url, right.stdout)
    for url in ("https://github.com/fourpoint669/sd-forge-fork.git", "https://github.com/fourpoint669/not-sd-forge.git",
                "https://github.com/sd-forge/other.git"):
        git("remote", "set-url", "origin", url)
        refused = run()
        assert refused.returncode == 1 and "unexpected remote" in refused.stdout, (url, refused.stdout)


@posix_only
def test_a_folder_unpacked_inside_another_repository_is_not_mistaken_for_a_clone(tmp_path):
    outer = tmp_path / "outer"
    outer.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=outer, check=True)
    subprocess.run(["git", "remote", "add", "origin", "https://github.com/someone-else/other.git"], cwd=outer, check=True)
    d = outer / "sd-forge"
    shutil.copytree(ROOT, d, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", ".pytest_cache"))
    env = {k: v for k, v in os.environ.items() if k != "SD_PROJECTS_DIR"}
    p = subprocess.run([sys.executable, "-I", str(d / "engine" / "check_repo.py"), "--projects-root", str(d / "projects")],
                       cwd=tmp_path, env=env, capture_output=True, text=True)
    assert p.returncode == 0 and "unexpected remote" not in p.stdout, p.stdout


# ---- Codex (and what the closing message says) -------------------------------------------------------------------------

CODEX_LINKS = [".codex/skills/sd-model", ".codex/skills/sd-explorer"]


@posix_only
def test_codex_install_links_the_same_skill_folders_and_is_idempotent(tmp_path):
    first = _sh(INSTALL, tmp_path, "--codex", codex=True)
    assert first.returncode == 0, first.stderr
    for link, name in zip(CODEX_LINKS, ("sd-model", "sd-explorer")):
        assert os.readlink(tmp_path / link) == os.path.join(ROOT, ".claude", "skills", name)
        assert (tmp_path / link / "SKILL.md").exists() and (tmp_path / link / "agents" / "openai.yaml").exists()
    assert first.stdout.count("linked:") == 6
    snapshot = _tree_codex(tmp_path)
    second = _sh(INSTALL, tmp_path, codex=True)
    assert second.returncode == 0 and _tree_codex(tmp_path) == snapshot and "linked:" not in second.stdout.replace("already linked", "")


def _tree_codex(home):
    return {**_tree(home), **_tree_of(os.path.join(home, ".codex"), home)} if os.path.isdir(os.path.join(home, ".codex")) else _tree(home)


@posix_only
def test_codex_home_variable_is_honoured(tmp_path):
    # --codex explicitly: this test is about the variable, not about detection. Without it the installer stays in
    # auto mode, and because $CODEX_HOME does not exist yet, detection falls through to `command -v codex` - which
    # is on PATH on a machine that has Codex and absent on CI, so the test would pass or fail by machine.
    p = _sh(INSTALL, tmp_path / "home", "--codex", codex=True,
            env_extra={"CODEX_HOME": str(tmp_path / "elsewhere")})
    assert p.returncode == 0, p.stderr
    assert os.path.islink(tmp_path / "elsewhere" / "skills" / "sd-model")
    assert not (tmp_path / "home" / ".codex").exists()
    assert _sh(UNINSTALL, tmp_path / "home", env_extra={"CODEX_HOME": str(tmp_path / "elsewhere")}).returncode == 0
    assert not os.path.lexists(tmp_path / "elsewhere" / "skills" / "sd-model")


@posix_only
def test_codex_is_detected_by_its_folder_and_can_be_declined(tmp_path):
    (tmp_path / ".codex").mkdir()
    auto = _sh(INSTALL, tmp_path, codex=True)                     # auto: ~/.codex exists
    assert auto.returncode == 0 and os.path.islink(tmp_path / ".codex" / "skills" / "sd-model")
    other = tmp_path / "other"
    (other / ".codex").mkdir(parents=True)
    declined = _sh(INSTALL, other, "--no-codex", codex=True)
    assert declined.returncode == 0 and not os.path.lexists(other / ".codex" / "skills" / "sd-model")
    assert "Using Codex too? Run this script again with --codex" in declined.stdout


@posix_only
def test_a_real_folder_in_the_codex_skills_refuses_the_whole_install(tmp_path):
    (tmp_path / ".codex" / "skills" / "sd-model").mkdir(parents=True)
    (tmp_path / ".codex" / "skills" / "sd-model" / "SKILL.md").write_text("mine")
    before = _tree_of(str(tmp_path / ".codex"), tmp_path)
    p = _sh(INSTALL, tmp_path, "--codex", codex=True)
    assert p.returncode == 1 and "REFUSED" in p.stderr and ".codex/skills/sd-model" in p.stderr and "Nothing was changed" in p.stderr
    assert _tree_of(str(tmp_path / ".codex"), tmp_path) == before and not (tmp_path / ".claude").exists() and not (tmp_path / ".config").exists()


@posix_only
def test_uninstall_removes_codex_links_and_leaves_foreign_ones(tmp_path):
    assert _sh(INSTALL, tmp_path, "--codex", codex=True).returncode == 0
    os.remove(tmp_path / ".codex" / "skills" / "sd-explorer")
    os.symlink("/somewhere/else", tmp_path / ".codex" / "skills" / "sd-explorer")
    p = _sh(UNINSTALL, tmp_path)
    assert p.returncode == 0 and "removed:   " + str(tmp_path / ".codex/skills/sd-model") in p.stdout
    assert os.readlink(tmp_path / ".codex" / "skills" / "sd-explorer") == "/somewhere/else"
    assert "left:" in p.stdout


@posix_only
def test_the_closing_message_reflects_what_was_installed(tmp_path):
    claude_only = _sh(INSTALL, tmp_path / "a")
    assert '/sd-model "' in claude_only.stdout and "$sd-model" not in claude_only.stdout
    both = _sh(INSTALL, tmp_path / "b", "--codex", codex=True)
    for text in ('/sd-model "', '$sd-model "', "$sd-explorer <folder", "signed in with your ChatGPT account"):
        assert text in both.stdout, text
    for out in (claude_only.stdout, both.stdout):                 # the ChatGPT limit is stated either way
        assert "ChatGPT in a browser or phone app cannot run these" in out and "use Codex" in out


@posix_only
def test_skills_say_how_each_tool_invokes_them_and_carry_codex_metadata():
    for name, path in SKILLS.items():
        text = open(path, encoding="utf-8").read()
        assert f"`/{name}`" in text and f"`${name}`" in text and "Codex" in text, name
        yaml = open(os.path.join(os.path.dirname(path), "agents", "openai.yaml"), encoding="utf-8").read()
        assert f'display_name: "{name}"' in yaml and "short_description:" in yaml


# ---- setup.command: the one executable ---------------------------------------------------------------------------------

SETUP = os.path.join(ROOT, "setup.command")


def _setup(repo, home, *args, path=None):
    """Run a copy of setup.command with a temporary HOME. No terminal is attached, so it never asks a question."""
    env = {"PATH": path or os.environ["PATH"], "HOME": str(home), "SD_INSTALL_NO_DIALOG": "1"}
    return subprocess.run([shutil.which("bash"), str(repo / "setup.command"), *args], env=env, cwd=str(home), capture_output=True, text=True)


def _have_python():
    return subprocess.run([shutil.which("bash"), INSTALL, "--check-python"], capture_output=True).returncode == 0


needs_python = pytest.mark.skipif(not _have_python(), reason="no supported Python on this machine")


@posix_only
def test_setup_command_is_one_executable_file():
    assert os.access(SETUP, os.X_OK) and open(SETUP).readline().startswith("#!/usr/bin/env bash")
    if os.path.isdir(os.path.join(ROOT, ".git")):                       # a zip has no git; the file mode is what a zip keeps
        assert subprocess.run(["git", "ls-files", "-s", "setup.command"], cwd=ROOT, capture_output=True, text=True).stdout.startswith("100755")


@needs_python
@posix_only
def test_setup_from_downloads_copies_to_a_permanent_folder_and_installs_from_there(tmp_path):
    home = tmp_path / "home"
    repo = _mini_repo(tmp_path, "sd-forge-main", parent=home / "Downloads")
    p = _setup(repo, home, "--move", "--no-python", "--no-codex")
    assert p.returncode == 0, p.stdout + p.stderr
    dest = home / "sd-forge"
    assert (dest / "engine" / "validate.py").exists() and (repo / "engine" / "validate.py").exists()   # the original is kept
    assert (home / ".config" / "sd-forge" / "home").read_text() == str(dest) + "\n"
    assert os.readlink(home / ".claude" / "skills" / "sd-model") == str(dest / ".claude" / "skills" / "sd-model")
    assert "copied:" in p.stdout and "no longer needed" in p.stdout and "sd-forge is installed" in p.stdout


@needs_python
@posix_only
def test_setup_installs_in_place_when_nobody_can_be_asked_and_says_so(tmp_path):
    home = tmp_path / "home"
    repo = _mini_repo(tmp_path, "sd-forge-main", parent=home / "Downloads")
    p = _setup(repo, home, "--no-python", "--no-codex")                       # no terminal, no --move
    assert p.returncode == 0 and "may not be a permanent place" in p.stdout and "--move" in p.stdout
    assert not (home / "sd-forge").exists()
    assert (home / ".config" / "sd-forge" / "home").read_text() == str(repo) + "\n"


@needs_python
@posix_only
def test_setup_here_never_copies_and_a_normal_folder_is_left_alone(tmp_path):
    home = tmp_path / "home"
    in_downloads = _mini_repo(tmp_path, "a", parent=home / "Downloads")
    p = _setup(in_downloads, home, "--move", "--here", "--no-python", "--no-codex")     # --here wins over --move
    assert p.returncode == 0 and not (home / "sd-forge").exists() and "copied:" not in p.stdout
    home2 = tmp_path / "home2"
    permanent = _mini_repo(tmp_path, "sd-forge", parent=home2 / "code")
    q = _setup(permanent, home2, "--move", "--no-python", "--no-codex")
    assert q.returncode == 0 and "copied:" not in q.stdout and "may not be a permanent place" not in q.stdout
    assert (home2 / ".config" / "sd-forge" / "home").read_text() == str(permanent) + "\n"


@needs_python
@posix_only
def test_setup_refuses_to_overwrite_an_existing_destination_and_installs_nothing(tmp_path):
    home = tmp_path / "home"
    repo = _mini_repo(tmp_path, "sd-forge-main", parent=home / "Downloads")
    (home / "sd-forge").mkdir(parents=True)
    (home / "sd-forge" / "mine.txt").write_text("keep")
    p = _setup(repo, home, "--move", "--no-python", "--no-codex")
    assert p.returncode == 1 and "already exists" in p.stderr and "--here" in p.stderr
    assert (home / "sd-forge" / "mine.txt").read_text() == "keep" and sorted(os.listdir(home / "sd-forge")) == ["mine.txt"]
    assert not (home / ".claude").exists() and not (home / ".config").exists()


@posix_only
def test_setup_stops_before_copying_anything_when_there_is_no_supported_python(tmp_path):
    home = tmp_path / "home"
    repo = _mini_repo(tmp_path, "sd-forge-main", parent=home / "Downloads")
    p = _setup(repo, home, "--move", path=_tools(tmp_path, {}))
    assert p.returncode == 1 and "no usable Python found" in p.stderr + p.stdout
    assert not (home / "sd-forge").exists() and not (home / ".claude").exists() and not (home / ".config").exists()


@posix_only
def test_setup_refuses_an_unknown_option_before_copying_anything(tmp_path):
    """A typo in a forwarded option used to be found only by install-skills.sh, after the folder had been copied."""
    home = tmp_path / "home"
    repo = _mini_repo(tmp_path, "sd-forge-main", parent=home / "Downloads")
    p = _setup(repo, home, "--move", "--no-python", "--forse")
    assert p.returncode == 2 and "--forse" in p.stderr and "usage:" in p.stderr
    assert not (home / "sd-forge").exists() and not (home / ".claude").exists() and not (home / ".config").exists()


@posix_only
def test_setup_names_the_copy_it_made_when_the_install_then_fails(tmp_path):
    """The copy is made before the install runs; a failure afterwards must not leave the user guessing where it went."""
    home = tmp_path / "home"
    repo = _mini_repo(tmp_path, "sd-forge-main", parent=home / "Downloads")
    (home / ".claude" / "skills" / "sd-model").mkdir(parents=True)       # a real directory: the installer refuses to link
    p = _setup(repo, home, "--move", "--no-python", "--no-codex")
    assert p.returncode == 1 and "REFUSED" in p.stderr
    dest = home / "sd-forge"
    assert dest.is_dir() and "copied:" in p.stdout                       # the copy happened before the refusal
    assert str(dest) in p.stdout and "installed nothing" in p.stdout


@needs_python
@posix_only
def test_setup_passes_options_through_and_installs_codex_when_asked(tmp_path):
    home = tmp_path / "home"
    repo = _mini_repo(tmp_path, "sd-forge", parent=home / "code")
    p = _setup(repo, home, "--no-python", "--codex")
    assert p.returncode == 0, p.stdout + p.stderr
    assert os.path.islink(home / ".codex" / "skills" / "sd-model") and "$sd-model" in p.stdout


def _real_newer_python():
    for minor in range(13, 20):
        p = shutil.which(f"python3.{minor}")
        if p:
            return p
    return None


@posix_only
def test_a_real_newer_python_is_installed_only_after_it_reproduces_the_real_example(tmp_path):
    """The machine has only a newer Python on the PATH (3.12 and 3.11 are hidden): the installer builds the environment
    with it, validates the shipped example and compares the result files with the committed ones."""
    newer = _real_newer_python()
    if not newer:
        pytest.skip("no Python newer than the supported ones on this machine")
    if not _pypi_reachable():
        pytest.skip("pypi.org is not reachable")
    repo = _mini_repo(tmp_path)
    ex = repo / "projects" / "bass-b2b-adoption"
    for f in ("model", "assumptions_register.md", "summary.md", "sources.md"):
        src = os.path.join(ROOT, "projects", "bass-b2b-adoption", f)
        if os.path.isdir(src):
            shutil.copytree(src, ex / f, dirs_exist_ok=True)
        elif os.path.exists(src):
            shutil.copy(src, ex / f)
    shutil.copy(os.path.join(ROOT, "engine", "requirements.txt"), repo / "engine" / "requirements.txt")
    shutil.rmtree(repo / "engine")
    shutil.copytree(os.path.join(ROOT, "engine"), repo / "engine", ignore=shutil.ignore_patterns("__pycache__", "tests"))
    tools = _tools(tmp_path, {})
    os.symlink(newer, os.path.join(tools, os.path.basename(newer)))
    env = {"PATH": tools, "HOME": str(tmp_path / "h"), "SD_INSTALL_NO_DIALOG": "1"}
    p = subprocess.run([shutil.which("bash"), str(repo / "install-skills.sh"), "--no-codex"], env=env, capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "reproduces the shipped example exactly" in p.stdout and "created:" in p.stdout
    assert (repo / ".venv" / ".sd-forge-verified").read_text().startswith("python=3.")
    assert os.path.islink(tmp_path / "h" / ".claude" / "skills" / "sd-model")



# ---- regression pass: the installer must never delete what it did not create, and must leave no half state ---------------

def _fake_interpreter(path, version="3.12", pip_ok=True):
    """A fake interpreter: reports `version`, makes a virtual environment by copying itself, and 'installs' packages."""
    body = ('#!/bin/sh\ncase "$*" in\n  *"-m venv"*) mkdir -p "$3/bin"; cp "$0" "$3/bin/python"; exit 0 ;;\n'
            f'  *sys.version_info*) echo {version}; exit 0 ;;\n  *"import pysd"*) exit 0 ;;\n  *"-m pip"*) ' + ('exit 0' if pip_ok else 'echo pip-failed >&2; exit 1') + ' ;;\nesac\nexit 1\n')
    open(path, "w").write(body)
    os.chmod(path, 0o755)


def _install_with(repo, home, bindir, *args, env_extra=None):
    env = {"PATH": bindir, "HOME": str(home), "SD_INSTALL_NO_DIALOG": "1", **(env_extra or {})}
    return subprocess.run([shutil.which("bash"), str(repo / "install-skills.sh"), "--no-codex", *args], env=env, capture_output=True, text=True)


@posix_only
def test_a_dot_venv_that_is_the_users_file_is_never_deleted(tmp_path):
    repo = _mini_repo(tmp_path)
    (repo / ".venv").write_text("precious\n")
    bindir = _tools(tmp_path, {})
    _fake_interpreter(os.path.join(bindir, "python3.12"))
    p = _install_with(repo, tmp_path / "h", bindir)
    assert (repo / ".venv").read_text() == "precious\n"
    assert p.returncode == 1 and ".venv" in p.stderr and "not a Python environment" in p.stderr
    assert not (tmp_path / "h").exists()


@posix_only
def test_a_dot_venv_folder_with_user_files_is_never_deleted_even_when_pip_fails(tmp_path):
    repo = _mini_repo(tmp_path)
    (repo / ".venv").mkdir()
    (repo / ".venv" / "mine.txt").write_text("precious\n")
    bindir = _tools(tmp_path, {})
    _fake_interpreter(os.path.join(bindir, "python3.12"), pip_ok=False)
    p = _install_with(repo, tmp_path / "h", bindir)
    assert (repo / ".venv" / "mine.txt").read_text() == "precious\n"
    assert p.returncode == 1 and not (tmp_path / "h").exists()


@posix_only
def test_an_empty_dot_venv_folder_is_used_and_a_failed_install_leaves_no_environment_behind(tmp_path):
    repo = _mini_repo(tmp_path)
    (repo / ".venv").mkdir()
    bindir = _tools(tmp_path, {})
    _fake_interpreter(os.path.join(bindir, "python3.12"))
    ok = _install_with(repo, tmp_path / "h", bindir)
    assert ok.returncode == 0 and (repo / ".venv" / "bin" / "python").exists(), ok.stderr
    other = _mini_repo(tmp_path, "other")
    _fake_interpreter(os.path.join(bindir, "python3.12"), pip_ok=False)
    bad = _install_with(other, tmp_path / "h2", bindir)
    assert bad.returncode == 1 and not (other / ".venv").exists() and not (tmp_path / "h2").exists()


@pytest.mark.parametrize("supported", [True, False])
@posix_only
def test_interpreter_paths_with_spaces_stay_whole(tmp_path, supported):
    repo = _mini_repo(tmp_path)
    bindir = _tools(tmp_path / "with space", {}) if False else None
    spaced = tmp_path / "py tools"
    spaced.mkdir()
    for tool in ("dirname", "head", "sed", "awk", "readlink", "ln", "rm", "mkdir", "cat", "grep", "bash", "cp", "sort", "mktemp", "cmp", "mv", "rmdir", "chmod", "touch", "tr", "cut", "ls", "date", "id", "tail", "wc", "find"):
        if shutil.which(tool):
            os.symlink(shutil.which(tool), spaced / tool)
    results = tmp_path / "results"
    shutil.copytree(os.path.join(ROOT, "projects", "bass-b2b-adoption"), results)
    if supported:
        _fake_interpreter(str(spaced / "python3.12"))
    else:
        fake = spaced / "python3.14"
        fake.write_text(FAKE_PYTHON)
        fake.chmod(0o755)
    env = {"PATH": str(spaced), "HOME": str(tmp_path / "h"), "SD_INSTALL_NO_DIALOG": "1", "FAKE_RESULTS": str(results)}
    chk = subprocess.run([shutil.which("bash"), str(repo / "install-skills.sh"), "--check-python"], env=env, capture_output=True, text=True)
    assert chk.returncode == 0 and chk.stdout.startswith(str(spaced / ("python3.12" if supported else "python3.14")) + " ("), chk.stdout
    p = subprocess.run([shutil.which("bash"), str(repo / "install-skills.sh"), "--no-codex"], env=env, capture_output=True, text=True)
    assert p.returncode == 0 and (repo / ".venv" / "bin" / "python").exists(), p.stdout + p.stderr


def _snapshot(home):
    out = {}
    for dp, dn, fn in os.walk(home):
        for n in dn + fn:
            q = os.path.join(dp, n)
            out[os.path.relpath(q, home)] = os.readlink(q) if os.path.islink(q) else (open(q).read() if os.path.isfile(q) else "<dir>")
    return out


@posix_only
def test_a_failure_after_some_links_were_made_restores_the_previous_state_exactly(tmp_path):
    """The Claude links succeed, creating the Codex link then fails (its folder is read-only): nothing may stay changed."""
    home = tmp_path / "h"
    (home / ".codex" / "skills").mkdir(parents=True)
    (home / ".claude" / "skills").mkdir(parents=True)
    os.symlink("/somewhere/else", home / ".claude" / "skills" / "sd-model")           # a link the --force run will replace
    (home / ".config" / "sd-forge").mkdir(parents=True)
    (home / ".config" / "sd-forge" / "home").write_text("/another/checkout\n")        # the previous home
    os.chmod(home / ".codex" / "skills", 0o555)
    before = _snapshot(home)
    try:
        p = _sh(INSTALL, home, "--codex", "--force", codex=True)
    finally:
        os.chmod(home / ".codex" / "skills", 0o755)
    assert p.returncode != 0
    assert _snapshot(home) == before, p.stdout + p.stderr


@posix_only
def test_a_failure_on_a_fresh_home_leaves_no_directories_behind(tmp_path):
    home = tmp_path / "h"
    (home / ".codex" / "skills").mkdir(parents=True)
    os.chmod(home / ".codex" / "skills", 0o555)
    try:
        p = _sh(INSTALL, home, "--codex", codex=True)
    finally:
        os.chmod(home / ".codex" / "skills", 0o755)
    assert p.returncode != 0
    assert sorted(_snapshot(home)) == [".codex", ".codex/skills"], sorted(_snapshot(home))


@posix_only
def test_when_dot_claude_is_a_file_nothing_else_is_created(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    (home / ".claude").write_text("i am a file")
    p = _sh(INSTALL, home)
    assert p.returncode != 0 and sorted(os.listdir(home)) == [".claude"] and (home / ".claude").read_text() == "i am a file", p.stderr


@posix_only
def test_setup_with_no_python_option_works_without_any_python_on_the_path(tmp_path):
    home = tmp_path / "h"
    repo = _mini_repo(tmp_path, "sd-forge", parent=home / "code")
    p = _setup(repo, home, "--no-python", "--no-codex", path=_tools(tmp_path, {}))
    assert p.returncode == 0, p.stdout + p.stderr
    assert (home / ".config" / "sd-forge" / "home").read_text() == str(repo) + "\n"


@posix_only
def test_setup_refuses_a_dangling_symlink_as_destination_and_keeps_it(tmp_path):
    home = tmp_path / "h"
    repo = _mini_repo(tmp_path, "sd-forge-main", parent=home / "Downloads")
    os.symlink(tmp_path / "nowhere", home / "sd-forge")
    p = _setup(repo, home, "--move", "--no-python", "--no-codex")
    assert p.returncode == 1 and "already exists" in p.stderr
    assert os.path.islink(home / "sd-forge") and not (tmp_path / "nowhere").exists() and not (home / ".claude").exists()


def _pty_run(script, home, cwd, args, answers=(), timeout=40):
    import pty, select, time
    env = {"PATH": os.environ["PATH"], "HOME": str(home), "SD_INSTALL_NO_DIALOG": "1", "TERM": "xterm"}
    pid, fd = pty.fork()
    if pid == 0:
        os.chdir(cwd)
        os.execve(shutil.which("bash"), ["bash", str(script), *args], env)
    out, sent, end = b"", 0, time.time() + timeout
    while time.time() < end:
        r, _, _ = select.select([fd], [], [], 0.5)
        if r:
            try:
                data = os.read(fd, 4096)
            except OSError:
                break
            if not data:
                break
            out += data
            if sent < len(answers) and out.decode("utf-8", "replace").rstrip().endswith(("]", "window.")):
                time.sleep(0.2)
                os.write(fd, answers[sent].encode())
                sent += 1
    try:
        done, status = os.waitpid(pid, os.WNOHANG)
        if not done:                                                              # never leave a stuck child behind
            os.kill(pid, 9)
            _, status = os.waitpid(pid, 0)
    except ChildProcessError:
        status = 0
    return out.decode("utf-8", "replace"), os.waitstatus_to_exitcode(status)


@posix_only
def test_the_double_click_pause_works_when_home_is_reached_through_a_symlink(tmp_path):
    real = tmp_path / "real home"
    real.mkdir()
    link = tmp_path / "home link"
    os.symlink(real, link)
    repo = _mini_repo(tmp_path, "sd-forge", parent=real / "code")
    out, code = _pty_run(repo / "setup.command", link, real, ["--no-python", "--no-codex"], answers=["\n"])
    assert code == 0 and "Press Return to close this window" in out, out[-300:]


def _failing_ln_path(tmp_path, fail_on):
    """A PATH whose `ln` fails on its Nth call: a failure the preflight cannot foresee, in the middle of the link phase."""
    tools = _tools(tmp_path, {})
    os.remove(os.path.join(tools, "ln"))
    counter = tmp_path / "ln-count"
    counter.write_text("0")
    real_ln = shutil.which("ln")
    script = os.path.join(tools, "ln")
    open(script, "w").write(f'#!/bin/sh\nn=$(cat "{counter}"); n=$((n+1)); echo $n > "{counter}"\n[ "$n" -eq {fail_on} ] && {{ echo "ln: injected failure" >&2; exit 1; }}\nexec "{real_ln}" "$@"\n')
    os.chmod(script, 0o755)
    return tools


@posix_only
def test_an_unforeseen_failure_in_the_middle_of_the_links_rolls_everything_back_on_a_fresh_home(tmp_path):
    home = tmp_path / "h"
    home.mkdir()
    bindir = _failing_ln_path(tmp_path, 3)                                      # the third link fails: two are already made
    p = subprocess.run([shutil.which("bash"), INSTALL, "--no-python", "--no-codex"], env={"PATH": bindir, "HOME": str(home), "SD_INSTALL_NO_DIALOG": "1"},
                       capture_output=True, text=True)
    assert p.returncode != 0 and "injected failure" in p.stderr
    assert os.listdir(home) == [], _snapshot(home)                              # no links, no home file, no directories, no temp files


@posix_only
def test_an_unforeseen_failure_restores_replaced_links_and_the_previous_home_file(tmp_path):
    home = tmp_path / "h"
    (home / ".claude" / "skills").mkdir(parents=True)
    os.symlink("/somewhere/else", home / ".claude" / "skills" / "sd-model")
    (home / ".config" / "sd-forge").mkdir(parents=True)
    (home / ".config" / "sd-forge" / "home").write_text("/another/checkout\n")
    before = _snapshot(home)
    bindir = _failing_ln_path(tmp_path, 4)                                      # sd-model replaced, sd-explorer made, a command link, then failure
    p = subprocess.run([shutil.which("bash"), INSTALL, "--no-python", "--no-codex", "--force"],
                       env={"PATH": bindir, "HOME": str(home), "SD_INSTALL_NO_DIALOG": "1"}, capture_output=True, text=True)
    assert p.returncode != 0
    assert _snapshot(home) == before, p.stdout + p.stderr


@posix_only
def test_a_folder_inside_a_symlinked_home_is_recognised_as_a_place_to_stay(tmp_path):
    real = tmp_path / "real home"
    real.mkdir()
    link = tmp_path / "home link"
    os.symlink(real, link)
    repo = _mini_repo(tmp_path, "sd-forge", parent=real / "code")                 # physical path under the physical HOME
    p = _setup(repo, link, "--no-python", "--no-codex")                           # no terminal: a question would show as a note
    assert p.returncode == 0 and "may not be a permanent place" not in p.stdout and "copied:" not in p.stdout, p.stdout
    downloads = _mini_repo(tmp_path, "sd-forge-main", parent=real / "Downloads")  # and Downloads is still recognised as temporary
    q = _setup(downloads, link, "--no-python", "--no-codex")
    assert "may not be a permanent place" in q.stdout, q.stdout


@posix_only
def test_a_pre_existing_empty_dot_venv_folder_survives_a_failed_install(tmp_path):
    repo = _mini_repo(tmp_path)
    (repo / ".venv").mkdir()
    os.chmod(repo / ".venv", 0o750)
    bindir = _tools(tmp_path, {})
    _fake_interpreter(os.path.join(bindir, "python3.12"), pip_ok=False)
    p = _install_with(repo, tmp_path / "h", bindir)
    assert p.returncode == 1 and (repo / ".venv").is_dir() and os.listdir(repo / ".venv") == []
    assert (os.stat(repo / ".venv").st_mode & 0o777) == 0o750                    # the folder itself, with its mode, is untouched


@posix_only
def test_a_dot_venv_folder_that_cannot_be_listed_is_not_taken_for_empty(tmp_path):
    repo = _mini_repo(tmp_path)
    (repo / ".venv").mkdir()
    (repo / ".venv" / "mine.txt").write_text("precious\n")
    os.chmod(repo / ".venv", 0)
    bindir = _tools(tmp_path, {})
    _fake_interpreter(os.path.join(bindir, "python3.12"))
    try:
        p = _install_with(repo, tmp_path / "h", bindir)
    finally:
        os.chmod(repo / ".venv", 0o755)
    assert p.returncode == 1 and "not a Python environment" in p.stderr
    assert (repo / ".venv" / "mine.txt").read_text() == "precious\n" and not (tmp_path / "h").exists()


@pytest.mark.parametrize("kind", ["file", "symlink"])
@posix_only
def test_the_temporary_home_file_never_overwrites_something_that_is_already_there(tmp_path, kind):
    """The shell's PID is predictable: a wrapper that exec's the installer knows it, and plants a file (or a link to a file)
    at the old temporary name before the installer starts. Nothing planted may be truncated, followed or removed."""
    home = tmp_path / "h"
    (home / ".config" / "sd-forge").mkdir(parents=True)
    victim = tmp_path / "victim.txt"
    victim.write_text("precious\n")
    wrapper = tmp_path / "wrap.sh"
    plant = f'ln -s "{victim}" "$HOME/.config/sd-forge/.home.$$"' if kind == "symlink" else 'echo precious > "$HOME/.config/sd-forge/.home.$$"'
    wrapper.write_text(f'#!/bin/bash\n{plant}\nexec bash "{INSTALL}" --no-python --no-codex\n')
    p = subprocess.run([shutil.which("bash"), str(wrapper)], env={"PATH": os.environ["PATH"], "HOME": str(home), "SD_INSTALL_NO_DIALOG": "1"},
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert victim.read_text() == "precious\n"
    planted = [f for f in os.listdir(home / ".config" / "sd-forge") if f.startswith(".home.")]
    assert len(planted) == 1                                                    # the planted entry is still there, untouched
    entry = home / ".config" / "sd-forge" / planted[0]
    assert (os.path.islink(entry) and os.readlink(entry) == str(victim)) if kind == "symlink" else entry.read_text() == "precious\n"
    assert (home / ".config" / "sd-forge" / "home").read_text() == str(INSTALL_DIR) + "\n"


@posix_only
def test_setup_forwards_exactly_the_options_install_skills_accepts():
    """setup.command checks the forwarded options itself, so that a typo is caught before the folder is copied. That
    means the two lists must not drift apart: an option install-skills.sh gains would be refused by setup.command."""
    def flags(path, after):
        """The options named by the case patterns of one arg loop (a pattern may be an alternation, '--a|--b')."""
        text = open(os.path.join(ROOT, path), encoding="utf-8").read()
        body = text[text.index(after):]
        body = body[:body.index("esac")]
        out = set()
        for line in body.splitlines():
            if ")" in line:                                  # only the pattern, never the usage text after it
                out |= set(re.findall(r"--[a-z][a-z-]*", line.split(")")[0]))
        return out
    accepted = flags("install-skills.sh", 'for a in "$@"; do')
    forwarded = flags("setup.command", "# Options are forwarded to install-skills.sh")
    assert accepted == forwarded, f"install-skills.sh accepts {sorted(accepted)}, setup.command forwards {sorted(forwarded)}"
    assert "--force" in accepted and "--check-python" in accepted           # the parse found something real
