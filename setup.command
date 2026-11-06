#!/usr/bin/env bash
# One executable for the whole setup. Unpack (or clone) sd-forge, then run this file:
#   - double-click it in Finder (macOS; if macOS blocks it the first time, right-click it and choose Open), or
#   - in a terminal:  bash setup.command
# It does everything in order:
#   1. checks that a usable Python exists and that every option is one install-skills.sh knows, before touching
#      anything (a supported 3.12 or 3.11, or a newer one, which is used only if the engine's self-check passes);
#   2. if this folder is somewhere it should not stay (Downloads, Desktop, a temporary folder or a mounted disk image),
#      offers to copy it to ~/sd-forge (or $SD_FORGE_DEST) and carries on from the copy, because the skills read the engine
#      from the folder they were installed from. The original is left alone; delete it yourself when you are happy;
#   3. runs install-skills.sh from the final folder: builds the Python environment, checks node, links the skills into
#      Claude Code and, if you have it, Codex, and shows what to type next.
# Options (everything else is passed to install-skills.sh, e.g. --codex, --no-codex, --force, --no-python):
#   --move      copy to the permanent folder without asking, if this folder is not already a good place
#   --here      never copy: install from where this folder is
#   --no-pause  do not wait for Return at the end (the wait only happens when this was started from Finder)
# Windows is not supported (these are shell scripts).
set -eu

move=ask
pause=auto
pass=()
for a in "$@"; do
  case "$a" in
    --move) move=yes ;;
    --here) move=no ;;
    --no-pause) pause=no ;;
    *) pass+=("$a") ;;
  esac
done

src="$(cd "$(dirname "$0")" && pwd -P)"
dest="${SD_FORGE_DEST:-$HOME/sd-forge}"

finish() {  # $1 exit status. A double-clicked .command runs in $HOME on a terminal; keep its window readable.
  status="$1"
  if [ "$pause" = auto ] && [ -t 0 ] && [ -t 1 ] && [ "${0##*.}" = command ] \
     && [ "$(pwd -P)" = "$(cd "$HOME" 2>/dev/null && pwd -P)" ]; then
    echo
    read -r -p "Press Return to close this window. " _ || true
  fi
  exit "$status"
}

[ -f "$src/install-skills.sh" ] && [ -f "$src/engine/validate.py" ] || { echo "ERROR: $src does not look like the sd-forge folder (install-skills.sh or engine/validate.py is missing)."; finish 1; }

# Options are forwarded to install-skills.sh, which would only reject an unknown one after this script has copied the
# folder; check them here instead, while nothing has been touched.
for a in ${pass[@]+"${pass[@]}"}; do
  case "$a" in
    --force|--no-python|--check-python|--codex|--no-codex) ;;
    *) echo "ERROR: unknown option $a" >&2
       echo "usage: $0 [--move | --here] [--no-pause] [--force] [--no-python] [--codex | --no-codex]" >&2
       finish 2 ;;
  esac
done

echo "sd-forge setup, from $src"
echo

# 1. Python first: if there is none, nothing has been copied or changed (--no-python means the user manages Python: no check)
skip_python_check=0
for a in ${pass[@]+"${pass[@]}"}; do
  if [ "$a" = --no-python ]; then skip_python_check=1; fi
done
if [ "$skip_python_check" = 0 ]; then
  if ! py_found="$(bash "$src/install-skills.sh" --check-python 2>&1)"; then
    printf '%s\n' "$py_found" >&2
    finish 1
  fi
  printf 'python:    %s\n' "$py_found"       # a newer-than-supported Python passes this gate: say which one is about to be used
fi

# 2. is this a place to stay?
temporary=0
home_phys="$(cd "$HOME" 2>/dev/null && pwd -P)" || home_phys="$HOME"      # $src is a physical path: compare it with the physical HOME too
case "$src" in
  "$HOME"/Downloads|"$HOME"/Downloads/*|"$HOME"/Desktop|"$HOME"/Desktop/*) temporary=1 ;;
  "$home_phys"/Downloads|"$home_phys"/Downloads/*|"$home_phys"/Desktop|"$home_phys"/Desktop/*) temporary=1 ;;
  "$HOME"/*|"$home_phys"/*) ;;                    # anywhere else under the home folder is a place to stay
  /tmp/*|/private/tmp/*|/var/folders/*|/private/var/folders/*|/Volumes/*) temporary=1 ;;
esac

run_from="$src"
if [ "$temporary" = 1 ] && [ "$move" != no ] && [ "$src" != "$dest" ]; then
  go=0
  if [ "$move" = yes ]; then
    go=1
  elif [ -t 0 ] && [ -t 1 ]; then
    echo "This folder is in a place where it may get deleted or moved:"
    echo "  $src"
    echo "sd-forge has to stay where it is installed, because the skills read the engine from there."
    read -r -p "Copy it to $dest and install from there? [Y/n] " answer || answer=n
    case "$answer" in ""|[Yy]*) go=1 ;; esac
  else
    echo "NOTE: $src may not be a permanent place, and no one is here to ask. Installing from it as it is; run with --move to copy it to $dest first."
  fi
  if [ "$go" = 1 ]; then
    if [ -e "$dest" ] || [ -L "$dest" ]; then
      echo "ERROR: $dest already exists. Rename or delete it, or run this again with --here to install from $src." >&2
      finish 1
    fi
    mkdir -p "$(dirname "$dest")"
    cp -R "$src" "$dest" || { echo "ERROR: could not copy to $dest" >&2; rm -rf "${dest:?}"; finish 1; }
    echo "copied:    $src -> $dest"
    run_from="$dest"
  fi
fi

# 3. install from the final folder
if bash "$run_from/install-skills.sh" ${pass[@]+"${pass[@]}"}; then
  if [ "$run_from" != "$src" ]; then
    echo
    echo "sd-forge now lives in $run_from. The original in $src is no longer needed; you can delete it."
  fi
  finish 0
else
  code=$?
  echo
  echo "Setup did not finish (see the message above). Nothing in your Claude Code or Codex folders was changed unless it says so."
  if [ "$run_from" != "$src" ]; then
    echo "This run copied the folder to $run_from and installed nothing. Delete that copy (rm -rf \"$run_from\") before"
    echo "running setup again from $src, or run setup from inside $run_from."
  fi
  finish "$code"
fi
