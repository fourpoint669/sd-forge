"""Where the engine and the projects are: path resolution only (no validation logic lives here).

Usage:  python -I engine/sd_paths.py home | projects-root [--projects-root DIR] | check

Engine home (the folder holding engine/, library/, raw/): env SD_FORGE_HOME, else the first line of the config file
~/.config/sd-forge/home that install-skills.sh writes. It must contain engine/validate.py; if neither source exists or
the path is wrong, PathError says which and how to fix it.

Projects root (the folder holding one subfolder per project): the --projects-root flag, else env SD_PROJECTS_DIR, else
the current working directory. One exception keeps the repository workflow unchanged: when the current directory IS
this engine home, the default is <home>/projects.

A project argument that is a path (has a separator, or exists as given) is used as given; a bare name that does not
exist as given is looked up under the projects root.

Standard library only; importable by every engine script.
"""
import os
import sys

SELF_HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_HOME = "SD_FORGE_HOME"
ENV_ROOT = "SD_PROJECTS_DIR"
FLAG = "--projects-root"
_override = None                       # set by a script that parsed --projects-root (see extract_flag)


class PathError(Exception):
    """The engine home or the projects root cannot be resolved; the message says what to do."""


def config_file():
    return os.path.join(os.path.expanduser("~"), ".config", "sd-forge", "home")


def _is_home(path):
    return os.path.isfile(os.path.join(path, "engine", "validate.py"))


def engine_home(env=None, config=None):
    """The engine home as an absolute path, or PathError. env / config default to the process environment and
    ~/.config/sd-forge/home (parameters exist for tests)."""
    env = os.environ if env is None else env
    config = config_file() if config is None else config
    if env.get(ENV_HOME):
        source, path = f"environment variable {ENV_HOME}", env[ENV_HOME]
    elif os.path.isfile(config):
        with open(config, encoding="utf-8") as f:
            path = f.readline().strip()
        source = f"config file {config}"
        if not path:
            raise PathError(f"{source} is empty. Run install-skills.sh from the sd-forge folder, or set {ENV_HOME}.")
    else:
        raise PathError(f"sd-forge home is not set: {ENV_HOME} is unset and {config} does not exist. "
                        f"Run install-skills.sh from the sd-forge folder, or set {ENV_HOME} to that folder.")
    path = os.path.abspath(os.path.expanduser(path))
    if not _is_home(path):
        raise PathError(f"{source} points to {path}, which has no engine/validate.py. "
                        f"Point it at the sd-forge folder (re-run install-skills.sh from there).")
    return path


def extract_flag(argv):
    """(argv without --projects-root DIR / --projects-root=DIR, the flag's value or None). Records the value so that
    projects_root() uses it for the rest of the process. A relative value is made absolute against the current
    directory NOW, before any script changes directory."""
    out, value, i = [], None, 0
    while i < len(argv):
        a = argv[i]
        if a == FLAG:
            if i + 1 >= len(argv):
                raise PathError(f"{FLAG} needs a folder")
            value, i = argv[i + 1], i + 2
        elif a.startswith(FLAG + "="):
            value, i = a[len(FLAG) + 1:], i + 1
        else:
            out.append(a)
            i += 1
    if value is not None:
        set_override(value)
    return out, value


def set_override(path):
    global _override
    _override = None if path is None else os.path.abspath(os.path.expanduser(path))


def projects_root_source(flag=None, env=None, cwd=None):
    """(absolute projects root, where it came from: 'flag' | 'env' | 'home' | 'cwd')."""
    env = os.environ if env is None else env
    flag = _override if flag is None else flag
    if flag:
        return os.path.abspath(os.path.expanduser(flag)), "flag"
    if env.get(ENV_ROOT):
        return os.path.abspath(os.path.expanduser(env[ENV_ROOT])), "env"
    cwd = os.getcwd() if cwd is None else cwd
    if os.path.realpath(cwd) == os.path.realpath(SELF_HOME):
        return os.path.join(SELF_HOME, "projects"), "home"
    return os.path.abspath(cwd), "cwd"


def projects_root(flag=None, env=None, cwd=None):
    return projects_root_source(flag, env, cwd)[0]


def resolve_project(arg, root=None):
    """Absolute path of the project named by a command-line argument (see the module docstring)."""
    if os.sep in arg or (os.altsep and os.altsep in arg) or os.path.exists(arg):
        return os.path.abspath(arg)
    return os.path.join(projects_root() if root is None else root, arg)


def git_entry_present(root):
    """True when `root` has a .git entry of any kind (folder, file, or a dangling link). Only "not found" means absent: any other
    error while looking (permissions, I/O) is raised, never read as "absent", because absent means "an unpacked zip"."""
    try:
        os.lstat(os.path.join(root, ".git"))
    except FileNotFoundError:
        return False
    return True


def root_problem(root, source):
    """Why an explicitly chosen projects root (flag or environment) cannot be used, or None. The current-folder default is not
    checked: an empty folder is a legitimate place to start."""
    if source not in ("flag", "env"):
        return None
    label = "the projects root given with --projects-root" if source == "flag" else "the projects root named by SD_PROJECTS_DIR"
    if not os.path.exists(root):
        return f"{label} ({root}) does not exist"
    if not os.path.isdir(root):
        return f"{label} ({root}) is not a folder"
    if not os.access(root, os.R_OK | os.X_OK):
        return f"{label} ({root}) cannot be read"
    return None


def project_problem(path, need_spec=True):
    """Why a project argument cannot be a project, or None."""
    if not os.path.isdir(path):
        return f"no project named {os.path.basename(os.path.normpath(path))}: {path} is not a folder"
    if need_spec and not os.path.isfile(os.path.join(path, "validation.toml")):
        return f"no project at {path}: it has no validation.toml"
    return None


def adopt_parent(project_dir):
    """A script given a project path while the projects root is only the current-directory default: the project's own
    folder is its projects root (the folder holding the projects it depends on)."""
    if projects_root_source()[1] == "cwd":
        set_override(os.path.dirname(os.path.abspath(project_dir)))


def main(argv):
    try:
        argv, _ = extract_flag(argv)
        cmd = argv[1] if len(argv) > 1 else ""
        if cmd == "home":
            print(engine_home())
        elif cmd == "projects-root":
            print(projects_root())
        elif cmd == "check":
            print(f"home={engine_home()}\nprojects_root={projects_root()}")
        else:
            print(__doc__)
            return 2
    except PathError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
