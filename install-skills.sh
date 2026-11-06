#!/usr/bin/env bash
# One-step install: unpack or clone sd-forge anywhere, run this script, then use the two skills from any folder, in
# Claude Code (/sd-model, /sd-explorer) and in OpenAI's Codex (the same skills, $sd-model, $sd-explorer).
#   1. finds a Python the engine supports (3.12, then 3.11) and builds the engine's environment in .venv from
#      engine/requirements.txt (skipped when it already works). With only a NEWER Python on the machine it builds the
#      environment with that, then validates the shipped example project and requires the same result files as the
#      committed ones; if they differ the environment is deleted and that Python is refused
#   2. checks that node is installed (the explorer build needs it) and says how to get it if not
#   3. writes this folder's path to ~/.config/sd-forge/home (the engine home, read by the skills and engine/sd_paths.py)
#   4. symlinks the two skills into ~/.claude/skills and the two slash commands into ~/.claude/commands (Claude Code),
#      and the two skills into $CODEX_HOME/skills, default ~/.codex/skills, when Codex is installed or --codex is given
#   5. says what to type next, in the terminal and (on a Mac or with zenity) in a dialog box
# ChatGPT in a browser or phone app cannot run local tools, so it cannot use these. Codex signs in with a ChatGPT account:
# that is the way to use the skills with one.
# Safe to run again. It never overwrites a file or folder that is not a symlink, and never replaces a link or a home
# that points somewhere else unless you pass --force (which replaces only symlinks and the home file). Nothing in
# ~/.claude or ~/.config is changed unless every target passes the check and the Python environment works.
# Options: --force   --no-python (skip steps 1-2, for people who manage their own environment)
#          --check-python (print the Python it would use, and whether it is supported or newer, and stop)
#          --codex (install for Codex even if it is not found)   --no-codex (Claude Code only)
# Undo the links with ./uninstall-skills.sh (the .venv folder is left in place).
# SD_INSTALL_NO_DIALOG=1 turns the dialog box off.
set -eu

# Supported interpreters, newest first. Keep in step with the "Python x or y" line of .claude/skills/sd-model/SKILL.md
# (a test compares them). A newer Python is accepted only after the self-check below passes; none of them is
# assumed to work.
SUPPORTED="3.12 3.11"

force=0
want_python=1
check_python=0
codex_mode=auto
for a in "$@"; do
  case "$a" in
    --force) force=1 ;;
    --no-python) want_python=0 ;;
    --check-python) check_python=1 ;;
    --codex) codex_mode=yes ;;
    --no-codex) codex_mode=no ;;
    *) echo "usage: $0 [--force] [--no-python] [--check-python] [--codex | --no-codex]" >&2; exit 2 ;;
  esac
done

src="$(cd "$(dirname "$0")" && pwd -P)"
[ -f "$src/engine/validate.py" ] || { echo "ERROR: $src has no engine/validate.py; run this script from the sd-forge folder" >&2; exit 1; }
for f in .claude/skills/sd-model .claude/skills/sd-explorer .claude/commands/sd-model.md .claude/commands/sd-explorer.md; do
  [ -e "$src/$f" ] || { echo "ERROR: $src/$f is missing" >&2; exit 1; }
done

py_version() {  # $1 interpreter -> "3.12" (empty if it cannot run)
  # macOS's /usr/bin/python3 is a stub that pops up an installer for the developer tools when they are missing: never run it then
  if [ "$1" = /usr/bin/python3 ] && command -v xcode-select >/dev/null 2>&1 && ! xcode-select -p >/dev/null 2>&1; then return 0; fi
  "$1" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true
}

find_python() {  # prints the first supported interpreter: python3.12, python3.11, then python3 / python if supported
  for v in $SUPPORTED; do
    if command -v "python$v" >/dev/null 2>&1; then command -v "python$v"; return 0; fi
  done
  for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1; then
      pv="$(py_version "$(command -v "$c")")"
      for v in $SUPPORTED; do
        if [ "$pv" = "$v" ]; then command -v "$c"; return 0; fi
      done
    fi
  done
  return 1
}

newer_pythons() {  # prints the path (one per line, spaces kept) of the first interpreter of each minor newer than every supported one, lowest first
  max=0
  for v in $SUPPORTED; do m="${v#3.}"; [ "$m" -gt "$max" ] && max="$m"; done
  seen=" "
  for c in $(compgen -c | grep -E '^python3(\.[0-9]+)?$|^python$' | sort -u); do
    p="$(command -v "$c" 2>/dev/null)" || continue
    pv="$(py_version "$p")"
    case "$pv" in 3.*) m="${pv#3.}" ;; *) continue ;; esac
    case "$m" in ''|*[!0-9]*) continue ;; esac
    [ "$m" -gt "$max" ] || continue
    case "$seen" in *" $m "*) continue ;; esac
    seen="$seen$m "
    printf '%s\t%s\n' "$m" "$p"
  done | sort -n | cut -f2-
}

no_python_help() {
  echo "ERROR: no usable Python found. sd-forge needs Python ${SUPPORTED// / or } (a newer one is accepted only if it reproduces the shipped example)." >&2
  echo "Install one, then run this script again:" >&2
  echo "  macOS (Homebrew):  brew install python@3.12" >&2
  echo "  any system:        https://www.python.org/downloads/ (pick a 3.12 release)" >&2
  echo "  with uv:           uv python install 3.12" >&2
}

# The self-check for a Python that is not on the supported list: validate the shipped example in a temporary copy and
# require its result files to equal the committed ones (validation also has to pass). $1 = the virtual environment.
self_check() {
  ex="$src/projects/bass-b2b-adoption"
  [ -f "$ex/validation.toml" ] && [ -f "$ex/mc_bands.csv" ] && [ -f "$ex/policy_results.csv" ] || return 1
  tmp="$(mktemp -d)" || return 1
  ok=1
  if cp -R "$ex" "$tmp/example" && rm -f "$tmp/example/mc_bands.csv" "$tmp/example/policy_results.csv" \
     && "$1/bin/python" -I "$src/engine/validate.py" "$tmp/example/validation.toml" >"$tmp/log" 2>&1 \
     && cmp -s "$tmp/example/mc_bands.csv" "$ex/mc_bands.csv" && cmp -s "$tmp/example/policy_results.csv" "$ex/policy_results.csv"; then
    ok=0
  fi
  rm -rf "${tmp:?}"
  return $ok
}

if [ "$check_python" = 1 ]; then
  if py="$(find_python)"; then echo "$py ($(py_version "$py"), supported)"; exit 0; fi
  if py="$(newer_pythons | head -n1)" && [ -n "$py" ]; then
    echo "$py ($(py_version "$py"), newer than the supported ones: it would be used only if the self-check passes)"; exit 0
  fi
  no_python_help; exit 1
fi

cfg_dir="$HOME/.config/sd-forge"
cfg="$cfg_dir/home"
links="$HOME/.claude/skills/sd-model|$src/.claude/skills/sd-model
$HOME/.claude/skills/sd-explorer|$src/.claude/skills/sd-explorer
$HOME/.claude/commands/sd-model.md|$src/.claude/commands/sd-model.md
$HOME/.claude/commands/sd-explorer.md|$src/.claude/commands/sd-explorer.md"

# Codex reads skills from $CODEX_HOME/skills (default ~/.codex/skills); the skill folders are the same ones Claude Code uses.
codex_home="${CODEX_HOME:-$HOME/.codex}"
use_codex=0
case "$codex_mode" in
  yes) use_codex=1 ;;
  auto) if [ -d "$codex_home" ] || command -v codex >/dev/null 2>&1; then use_codex=1; fi ;;
esac
if [ "$use_codex" = 1 ]; then
  links="$links
$codex_home/skills/sd-model|$src/.claude/skills/sd-model
$codex_home/skills/sd-explorer|$src/.claude/skills/sd-explorer"
fi

problems=0
# a status for each target: ok (already ours), new, replace (another symlink, needs --force), blocked (a real file or folder)
status_of() {  # $1 target, $2 source
  if [ -L "$1" ]; then
    if [ "$(readlink "$1")" = "$2" ]; then echo ok; else echo replace; fi
  elif [ -e "$1" ]; then echo blocked
  else echo new
  fi
}

dir_problem() {  # $1 = a folder the install must write into; prints why it cannot be (nothing if it can)
  p="$1"
  while [ ! -d "$p" ]; do
    if [ -e "$p" ] || [ -L "$p" ]; then echo "$p exists and is not a folder"; return 0; fi
    p="$(dirname "$p")"
  done
  if [ ! -w "$p" ] || [ ! -x "$p" ]; then echo "$p is not writable"; fi
}

cfg_status=new
if [ -L "$cfg" ] || [ -e "$cfg" ]; then
  if [ -f "$cfg" ] && [ ! -L "$cfg" ] && [ "$(head -n1 "$cfg")" = "$src" ]; then cfg_status=ok; else cfg_status=replace; fi
fi
if [ "$cfg_status" = replace ] && [ "$force" = 0 ]; then
  echo "REFUSED: $cfg already names a different home ($(head -n1 "$cfg" 2>/dev/null || echo 'not a file')). Re-run with --force to point it at $src." >&2
  problems=1
elif [ "$cfg_status" = replace ] && { [ -L "$cfg" ] || [ ! -f "$cfg" ]; }; then
  echo "REFUSED: $cfg is not a plain file; remove it yourself first." >&2
  problems=1
fi

while IFS='|' read -r target source; do
  st="$(status_of "$target" "$source")"
  if [ "$st" = blocked ]; then
    echo "REFUSED: $target exists and is not a symlink; move it away first." >&2
    problems=1
  elif [ "$st" = replace ] && [ "$force" = 0 ]; then
    echo "REFUSED: $target is a symlink to $(readlink "$target"), not to $source. Re-run with --force to replace it." >&2
    problems=1
  fi
  if [ "$st" != ok ] && [ "$st" != blocked ]; then            # a folder is only needed where something has to be written
    why="$(dir_problem "$(dirname "$target")")"
    if [ -n "$why" ]; then echo "REFUSED: cannot link $target: $why." >&2; problems=1; fi
  fi
done <<EOT
$links
EOT
if [ "$cfg_status" != ok ]; then
  why="$(dir_problem "$cfg_dir")"
  if [ -n "$why" ]; then echo "REFUSED: cannot write $cfg: $why." >&2; problems=1; fi
fi
[ "$problems" = 0 ] || { echo "Nothing was changed." >&2; exit 1; }

# ---- Python environment: the engine's own .venv ------------------------------------------------------------------------
venv="$src/.venv"
marker="$venv/.sd-forge-verified"
env_ok() { [ -x "$venv/bin/python" ] && "$venv/bin/python" -c 'import pysd, numpy, scipy, pandas, xarray, networkx, matplotlib' >/dev/null 2>&1; }
is_supported() { case " $SUPPORTED " in *" $1 "*) return 0 ;; esac; return 1; }
trusted() {  # the environment's Python is a supported one, or the self-check has passed for exactly this version
  pv="$(py_version "$venv/bin/python")"
  is_supported "$pv" || { [ -f "$marker" ] && grep -qx "python=$pv" "$marker"; }
}
verify_newer() {  # $1 = version; runs the self-check and records the result
  echo "Python $1 is newer than the ones sd-forge was developed on (${SUPPORTED// / or }). Checking that it reproduces the shipped example (about a minute) ..."
  if self_check "$venv"; then
    printf 'python=%s\nexample=bass-b2b-adoption: mc_bands.csv and policy_results.csv equal the committed ones\n' "$1" > "$marker"
    echo "verified:  Python $1 reproduces the shipped example exactly"
    return 0
  fi
  echo "The shipped example did NOT reproduce under Python $1 (or validation failed), so that Python is not used." >&2
  return 1
}
fail_existing() {
  echo "ERROR: $venv could not be used (details above). Delete that folder (rm -rf \"$venv\") and run this script again." >&2
  exit 1
}

if [ "$want_python" = 1 ]; then
  if env_ok && trusted; then
    echo "unchanged: $venv (Python $(py_version "$venv/bin/python"), packages present)"
  elif [ -x "$venv/bin/python" ]; then
    # an environment already exists: finish it, never delete it
    pv="$(py_version "$venv/bin/python")"
    echo "Installing the engine's Python packages into the existing $venv (Python ${pv:-?}) ..."
    "$venv/bin/python" -m pip install --quiet --disable-pip-version-check -r "$src/engine/requirements.txt" || fail_existing
    env_ok || { echo "The packages installed but the engine cannot import them." >&2; fail_existing; }
    if ! is_supported "$pv"; then verify_newer "$pv" || fail_existing; fi
    echo "updated:   $venv (Python $pv)"
  else
    # Only a path that is absent, or an empty folder, may be used: anything else at .venv is the user's, never ours to delete.
    venv_made=1                                   # 1: this run creates the folder and may remove it again on failure
    if [ -e "$venv" ] || [ -L "$venv" ]; then
      if [ -d "$venv" ] && [ ! -L "$venv" ] && listing="$(ls -A "$venv" 2>/dev/null)" && [ -z "$listing" ]; then
        venv_made=0                               # an empty folder that was already there: use it, never remove it
      else
        echo "ERROR: $venv exists but is not a Python environment (it is a file, a link, or a folder with other contents). Move or delete it yourself, then run this script again." >&2
        echo "Nothing was changed." >&2
        exit 1
      fi
    fi
    if py="$(find_python)"; then
      candidates="$py"
    else
      candidates="$(newer_pythons)"
      [ -n "$candidates" ] || { no_python_help; echo "Nothing was changed." >&2; exit 1; }
    fi
    built=0
    while IFS= read -r py; do
      [ -n "$py" ] || continue
      pv="$(py_version "$py")"
      echo "Creating the Python environment with $py ($pv) ..."
      if "$py" -m venv "$venv" && [ -x "$venv/bin/python" ]; then
        echo "Installing the engine's Python packages (about a minute, needs internet) ..."
        if "$venv/bin/python" -m pip install --quiet --disable-pip-version-check -r "$src/engine/requirements.txt" && env_ok; then
          if is_supported "$pv" || verify_newer "$pv"; then built=1; break; fi
        else
          echo "Installing the packages with $py failed (see the message above). Check your internet connection." >&2
        fi
      else
        echo "Could not create an environment with $py." >&2
      fi
      if [ "$venv_made" = 1 ]; then             # only what this run put there is removed; a folder that was already there stays
        rm -rf "${venv:?}"
      else
        find "$venv" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
      fi
    done <<EOT
$candidates
EOT
    if [ "$built" != 1 ]; then
      echo "ERROR: no Python on this machine produced a working, verified environment. Nothing was linked." >&2
      echo "Nothing was changed." >&2
      exit 1
    fi
    echo "created:   $venv (Python $(py_version "$venv/bin/python"))"
  fi
  if ! command -v node >/dev/null 2>&1; then
    echo
    echo "NOTE: node is not installed. Building the explorer page needs it. Install it from https://nodejs.org/ (or: brew install node) before using /sd-explorer."
    echo
  fi
else
  [ -x "$venv/bin/python" ] || echo "NOTE: $venv does not exist yet (--no-python): the skills will stop until the engine's Python environment is created."
fi

# ---- links and home: every change is journalled first, so a failure part-way puts everything back -----------------------
jdir="$(mktemp -d)" || { echo "ERROR: cannot create a temporary folder" >&2; exit 1; }
journal="$jdir/journal"
: > "$journal"
applying=0
tab="$(printf '\t')"
jlog() { printf '%s\t%s\t%s\n' "$1" "${2:-}" "${3:-}" >> "$journal"; }
rollback() {  # undo, newest first; carry on past a failed step, and never delete anything this run did not make
  set +e
  [ -s "$journal" ] || return 0
  echo "Setup failed part-way: putting back what this run changed ..." >&2
  sed -n '1!G;h;$p' "$journal" | while IFS="$tab" read -r kind a b; do
    case "$kind" in
      N) if [ -L "$a" ]; then rm -f "$a"; fi ;;                      # a link this run made
      R) rm -f "$a"; ln -s "$b" "$a" ;;                               # a link this run replaced: the old one comes back
      D) rmdir "$a" 2>/dev/null ;;                                    # a folder this run made: rmdir only removes it if it is empty
      T) rm -f "$a" ;;                                                # a temporary file
      C) if [ "$b" = none ]; then rm -f "$a"; else cp "$b" "$a"; fi ;; # the home file: restored, or removed if there was none
    esac
  done
  return 0
}
cleanup() {
  status=$?
  trap - EXIT
  if [ "$applying" = 1 ] && [ "$status" -ne 0 ]; then rollback; fi
  rm -rf "${jdir:?}"
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

mkdir_owned() {  # $1 = a folder: creates the missing parts one at a time, journalling each before it is made
  p="$1"
  todo=""
  while [ ! -d "$p" ]; do
    if [ -e "$p" ] || [ -L "$p" ]; then echo "ERROR: $p exists and is not a folder" >&2; return 1; fi
    todo="$p
$todo"
    p="$(dirname "$p")"
  done
  while IFS= read -r q; do
    [ -n "$q" ] || continue
    jlog D "$q"
    mkdir "$q" || return 1
  done <<EOF
$todo
EOF
}

applying=1
if [ "$cfg_status" = ok ]; then
  echo "unchanged: $cfg (already $src)"
else
  mkdir_owned "$cfg_dir"
  if [ -f "$cfg" ]; then cp "$cfg" "$jdir/cfg.bak"; jlog C "$cfg" "$jdir/cfg.bak"; else jlog C "$cfg" none; fi
  tmp="$(mktemp "$cfg_dir/.home.XXXXXX")" || { echo "ERROR: cannot create a temporary file in $cfg_dir" >&2; exit 1; }   # exclusive: never an existing name
  jlog T "$tmp"
  chmod 644 "$tmp"
  printf '%s\n' "$src" > "$tmp"
  mv -f "$tmp" "$cfg"                                                  # atomic: the old home file is never half-written
  echo "wrote:     $cfg -> $src"
fi
while IFS='|' read -r target source; do
  st="$(status_of "$target" "$source")"
  case "$st" in
    ok) echo "unchanged: $target (already linked)" ;;
    new) mkdir_owned "$(dirname "$target")"; jlog N "$target"; ln -s "$source" "$target"; echo "linked:    $target -> $source" ;;
    replace) old="$(readlink "$target" 2>/dev/null || true)"; jlog R "$target" "$old"; rm "$target"; ln -s "$source" "$target"; echo "relinked:  $target -> $source (was $old)" ;;
  esac
done <<EOT
$links
EOT
applying=0

# ---- what to do next ------------------------------------------------------------------------------------------------
msg_title="sd-forge is installed"
msg_body='In Claude Code, open it in any folder and type:

  /sd-model "your question, naming the decision it informs"
  /sd-explorer <folder of a finished model>'
if [ "$use_codex" = 1 ]; then
  msg_body="$msg_body

In Codex (terminal or desktop app, signed in with your ChatGPT account), type the same with a dollar sign:

  \$sd-model \"your question, naming the decision it informs\"
  \$sd-explorer <folder of a finished model>"
else
  msg_body="$msg_body

Using Codex too? Run this script again with --codex."
fi
msg_body="$msg_body

ChatGPT in a browser or phone app cannot run these (no access to your computer): use Codex, which signs in with the same ChatGPT account.

Models are written into the folder you start in. If a session is already open, start a new one first."
echo
echo "=================================================================="
echo "  $msg_title"
echo
printf '%s\n' "$msg_body" | sed 's/^/  /'
echo "=================================================================="

if [ -z "${SD_INSTALL_NO_DIALOG:-}" ] && [ -t 1 ]; then
  if command -v osascript >/dev/null 2>&1; then
    osascript -e "display dialog \"$(printf '%s' "$msg_body" | sed 's/\\/\\\\/g; s/"/\\"/g' | awk '{printf "%s\\n", $0}')\" with title \"$msg_title\" buttons {\"OK\"} default button \"OK\" giving up after 120" >/dev/null 2>&1 || true
  elif command -v zenity >/dev/null 2>&1 && [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]; then
    zenity --info --title="$msg_title" --text="$msg_body" >/dev/null 2>&1 || true
  fi
fi
