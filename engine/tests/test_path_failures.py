"""Fail-closed behaviour of the path and repository checks (engine/check_repo.py, engine/sd_paths.py and the scripts that take a
project): no git means a zip only when no repository metadata exists, an unreadable or dangling .git is an error, an
explicit projects root that does not exist is an error, and a project that does not exist is reported, never silently
accepted and never a traceback. Found in the regression pass over the installer work."""
import errno
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "engine"))
import sd_paths  # noqa: E402


@pytest.fixture(scope="module")
def repo_copy(tmp_path_factory):
    """A copy of the repository without .git, .venv and caches: what an unpacked zip holds."""
    d = tmp_path_factory.mktemp("zip") / "sd-forge"
    shutil.copytree(ROOT, d, ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", ".pytest_cache", "node_modules"))
    return d


@pytest.fixture
def clean(repo_copy):
    """Each test starts from a copy with no .git entry at all."""
    entry = repo_copy / ".git"
    if os.path.lexists(entry):
        shutil.rmtree(entry) if os.path.isdir(entry) and not os.path.islink(entry) else os.remove(entry)
    yield repo_copy
    if os.path.lexists(entry):
        shutil.rmtree(entry) if os.path.isdir(entry) and not os.path.islink(entry) else os.remove(entry)


def _empty_path(tmp_path):
    d = tmp_path / "no-git-here"
    d.mkdir(exist_ok=True)
    return str(d)


def _check_repo(repo, cwd, path=None):
    env = {k: v for k, v in os.environ.items() if k != "SD_PROJECTS_DIR"}
    if path is not None:
        env["PATH"] = path
    return subprocess.run([sys.executable, "-I", str(repo / "engine" / "check_repo.py"), "--projects-root", str(repo / "projects")],
                          cwd=cwd, env=env, capture_output=True, text=True)


# ---- the git checks ----------------------------------------------------------------------------------------------------

def test_a_zip_without_git_installed_is_checked_without_ever_starting_git(clean, tmp_path):
    p = _check_repo(clean, tmp_path, path=_empty_path(tmp_path))
    assert p.returncode == 0 and "errors=0" in p.stdout and "Traceback" not in p.stderr, p.stdout + p.stderr
    assert "not a git checkout" in p.stderr


def test_a_repository_without_a_working_git_is_an_error_not_a_zip(clean, tmp_path):
    (clean / ".git").mkdir()
    p = _check_repo(clean, tmp_path, path=_empty_path(tmp_path))                  # .git exists, no git binary
    assert p.returncode == 1 and "git" in p.stdout and "Traceback" not in p.stderr, p.stdout + p.stderr
    assert "not a git checkout" not in p.stderr


def test_an_empty_dot_git_folder_is_an_error_not_a_zip(clean, tmp_path):
    (clean / ".git").mkdir()
    p = _check_repo(clean, tmp_path)                                               # git is installed but the repository is broken
    assert p.returncode == 1 and "Traceback" not in p.stderr and "not a git checkout" not in p.stderr, p.stdout + p.stderr


def test_a_dangling_dot_git_symlink_is_an_error_not_a_zip(clean, tmp_path):
    os.symlink(tmp_path / "does-not-exist", clean / ".git")
    p = _check_repo(clean, tmp_path)
    assert p.returncode == 1 and "Traceback" not in p.stderr and "not a git checkout" not in p.stderr, p.stdout + p.stderr


def test_a_worktree_style_dot_git_file_still_gets_the_checks(clean, tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    git = lambda *a: subprocess.run(["git", *a], cwd=clean, capture_output=True, text=True, check=True)   # noqa: E731
    git("init", "-q", f"--separate-git-dir={real}")                                 # leaves a `.git` FILE pointing at `real`
    assert (clean / ".git").is_file()
    git("remote", "add", "origin", "https://github.com/someone/other-repo.git")
    wrong = _check_repo(clean, tmp_path)
    assert wrong.returncode == 1 and "unexpected remote" in wrong.stdout, wrong.stdout + wrong.stderr
    git("remote", "set-url", "origin", "https://github.com/anyone/sd-forge.git")
    right = _check_repo(clean, tmp_path)
    assert right.returncode == 0 and "errors=0" in right.stdout, right.stdout + right.stderr


@pytest.mark.parametrize("err", [errno.EACCES, errno.EIO])
def test_an_error_while_looking_at_dot_git_is_reported_never_read_as_absent(tmp_path, monkeypatch, err):
    real = os.lstat

    def boom(path, *a, **k):
        if os.path.basename(str(path)) == ".git":
            raise OSError(err, os.strerror(err), str(path))
        return real(path, *a, **k)
    monkeypatch.setattr(os, "lstat", boom)
    with pytest.raises(OSError):
        sd_paths.git_entry_present(str(tmp_path))
    monkeypatch.undo()
    assert sd_paths.git_entry_present(str(tmp_path)) is False                       # absent: FileNotFoundError only
    os.symlink(tmp_path / "nowhere", tmp_path / ".git")
    assert sd_paths.git_entry_present(str(tmp_path)) is True                        # dangling symlink: present


# ---- an explicit projects root must exist ------------------------------------------------------------------------------

def test_check_repo_refuses_an_explicit_projects_root_that_does_not_exist(tmp_path):
    for args, env in ((["--projects-root", str(tmp_path / "missing")], {}), ([], {"SD_PROJECTS_DIR": str(tmp_path / "missing")})):
        e = {k: v for k, v in os.environ.items() if k != "SD_PROJECTS_DIR"}
        e.update(env)
        p = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "engine", "check_repo.py"), "--require-explorer", *args], cwd=tmp_path,
                           env=e, capture_output=True, text=True)
        assert p.returncode == 1 and "does not exist" in p.stdout + p.stderr and "projects=0" not in p.stdout, p.stdout + p.stderr


def test_check_repo_refuses_an_explicit_projects_root_that_is_a_file(tmp_path):
    (tmp_path / "file").write_text("x")
    p = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "engine", "check_repo.py"), "--projects-root", str(tmp_path / "file")],
                       cwd=tmp_path, capture_output=True, text=True)
    assert p.returncode == 1 and "not a folder" in p.stdout + p.stderr, p.stdout + p.stderr


def test_the_current_folder_default_stays_permissive(tmp_path):
    e = {k: v for k, v in os.environ.items() if k != "SD_PROJECTS_DIR"}
    p = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "engine", "check_repo.py")], cwd=tmp_path, env=e, capture_output=True, text=True)
    assert p.returncode == 0 and "projects=0" in p.stdout


def test_root_problem_names_the_source():
    assert sd_paths.root_problem("/definitely/not/here", "flag").startswith("the projects root given with --projects-root")
    assert sd_paths.root_problem("/definitely/not/here", "env").startswith("the projects root named by SD_PROJECTS_DIR")
    assert sd_paths.root_problem("/definitely/not/here", "cwd") is None
    assert sd_paths.root_problem(ROOT, "flag") is None


# ---- a project that does not exist -------------------------------------------------------------------------------------

SCRIPTS = [("run_mode.py", ["check"]), ("explorer_intake.py", ["questions"]), ("explorer_intake.py", ["record"]),
           ("delay_audit.py", []), ("explorer_structure.py", []), ("build_explorer.py", [])]


@pytest.mark.parametrize("script,pre", SCRIPTS)
def test_a_project_that_does_not_exist_is_reported_by_every_script(tmp_path, script, pre):
    root = tmp_path / "projects"
    root.mkdir()
    e = {k: v for k, v in os.environ.items() if k != "SD_PROJECTS_DIR"}
    e["SD_PROJECTS_DIR"] = str(root)
    p = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "engine", script), *pre, "nope-project"], cwd=tmp_path, env=e,
                       capture_output=True, text=True)
    out = p.stdout + p.stderr
    assert p.returncode == 1 and "Traceback" not in out and "nope-project" in out and "no project" in out.lower(), (script, p.returncode, out[-400:])


def test_project_problem_helper(tmp_path):
    assert "no project" in sd_paths.project_problem(str(tmp_path / "x")).lower()
    (tmp_path / "x").mkdir()
    assert "validation.toml" in sd_paths.project_problem(str(tmp_path / "x"))
    (tmp_path / "x" / "validation.toml").write_text("")
    assert sd_paths.project_problem(str(tmp_path / "x")) is None


# ---- found by the fresh inspection of the first fix round ---------------------------------------------------------------

def _bass_copy(parent, with_page=False):
    shutil.copytree(os.path.join(ROOT, "projects", "bass-b2b-adoption"), os.path.join(parent, "bass-b2b-adoption"),
                    ignore=None if with_page else shutil.ignore_patterns("explorer.html", "explorer_parity.json"))


@pytest.mark.skipif(sys.platform == "win32", reason="Windows folder names cannot contain * or ?")
def test_a_projects_root_whose_name_contains_glob_characters_is_still_enumerated(tmp_path):
    root = tmp_path / "models[1] *?"
    root.mkdir()
    _bass_copy(root)                                                    # a real project, without its explorer page
    e = {k: v for k, v in os.environ.items() if k != "SD_PROJECTS_DIR"}
    p = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "engine", "check_repo.py"), "--require-explorer", "--projects-root", str(root)],
                       cwd=tmp_path, env=e, capture_output=True, text=True)
    assert p.returncode == 1 and "projects=1" in p.stdout and "no explorer.html" in p.stdout, p.stdout + p.stderr


def test_a_project_folder_whose_name_contains_glob_characters_is_checked(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    shutil.copytree(os.path.join(ROOT, "projects", "bass-b2b-adoption"), root / "proj[2]")
    import explorer_release as er
    assert [f for f in er.release_files(str(root / "proj[2]")) if f.endswith((".mdl", ".py"))], "the model files were not found"
    e = {k: v for k, v in os.environ.items() if k != "SD_PROJECTS_DIR"}
    p = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "engine", "check_repo.py"), "--projects-root", str(root)],
                       cwd=tmp_path, env=e, capture_output=True, text=True)
    assert p.returncode == 0 and "projects=1" in p.stdout and "errors=0" in p.stdout, p.stdout + p.stderr


@pytest.mark.skipif(sys.platform == "win32", reason="os.chmod cannot make a folder unreadable on Windows")
def test_an_unreadable_projects_root_is_an_error_not_an_empty_list(tmp_path):
    root = tmp_path / "locked"
    root.mkdir()
    os.chmod(root, 0)
    try:
        p = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "engine", "check_repo.py"), "--projects-root", str(root)], cwd=tmp_path,
                           capture_output=True, text=True)
    finally:
        os.chmod(root, 0o755)
    assert p.returncode == 1 and "cannot be read" in p.stdout + p.stderr and "projects=0" not in p.stdout, p.stdout + p.stderr


def test_run_mode_check_on_a_folder_that_is_not_a_project_is_an_error(tmp_path):
    (tmp_path / "empty-folder").mkdir()
    e = {k: v for k, v in os.environ.items() if k != "SD_PROJECTS_DIR"}
    e["SD_PROJECTS_DIR"] = str(tmp_path)
    p = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "engine", "run_mode.py"), "check", "empty-folder"], cwd=tmp_path, env=e,
                       capture_output=True, text=True)
    assert p.returncode == 1 and "validation.toml" in p.stdout + p.stderr, p.stdout + p.stderr
    ok = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "engine", "run_mode.py"), "check", os.path.join(ROOT, "projects", "bass-b2b-adoption")],
                        cwd=tmp_path, capture_output=True, text=True)
    assert ok.returncode == 0, ok.stdout + ok.stderr                    # a real full-mode project is still fine


# ---- the raw/_private exemption ----------------------------------------------------------------------------------------

def _raw_file(repo, folder):
    d = repo / "raw" / folder
    d.mkdir(parents=True, exist_ok=True)
    f = d / "unlisted.mdl"
    f.write_text("{UTF-8}\nx = 1 ~ Dmnl ~ |\n")
    return d, f


def test_a_file_under_raw_private_is_exempt_from_the_manifest(clean, tmp_path):
    d, _ = _raw_file(clean, "_private")
    try:
        p = _check_repo(clean, tmp_path)
        assert p.returncode == 0 and "errors=0" in p.stdout, p.stdout + p.stderr
    finally:
        shutil.rmtree(d)


def test_a_folder_whose_name_merely_starts_with_private_is_not_exempt(clean, tmp_path):
    """.gitignore covers raw/_private/ only, so a near-miss name used to be committed AND skipped by every check."""
    d, f = _raw_file(clean, "_private-wip")
    try:
        p = _check_repo(clean, tmp_path)
        assert p.returncode == 1, p.stdout + p.stderr
        assert "_private-wip/unlisted.mdl" in p.stdout and "not in MANIFEST" in p.stdout, p.stdout
    finally:
        shutil.rmtree(d)
