#!/usr/bin/env bash
# Undo install-skills.sh: removes the symlinks that point into this checkout (Claude Code's four, and Codex's two under
# $CODEX_HOME/skills, default ~/.codex/skills) and the home file if it names this checkout. Anything else (a real file or folder, a link to another place, a home naming another checkout) is left
# alone and reported.
set -eu

src="$(cd "$(dirname "$0")" && pwd -P)"
cfg_dir="$HOME/.config/sd-forge"
cfg="$cfg_dir/home"

remove_link() {  # $1 target, $2 source
  if [ -L "$1" ]; then
    if [ "$(readlink "$1")" = "$2" ]; then rm "$1"; echo "removed:   $1"
    else echo "left:      $1 (links to $(readlink "$1"), not to this checkout)"; fi
  elif [ -e "$1" ]; then echo "left:      $1 (not a symlink)"
  else echo "absent:    $1"
  fi
}

remove_link "$HOME/.claude/skills/sd-model" "$src/.claude/skills/sd-model"
remove_link "$HOME/.claude/skills/sd-explorer" "$src/.claude/skills/sd-explorer"
remove_link "$HOME/.claude/commands/sd-model.md" "$src/.claude/commands/sd-model.md"
remove_link "$HOME/.claude/commands/sd-explorer.md" "$src/.claude/commands/sd-explorer.md"
codex_home="${CODEX_HOME:-$HOME/.codex}"
# Codex links are removed only if they are ours; when none exist nothing is reported for Codex at all
for n in sd-model sd-explorer; do
  if [ -L "$codex_home/skills/$n" ] || [ -e "$codex_home/skills/$n" ]; then
    remove_link "$codex_home/skills/$n" "$src/.claude/skills/$n"
  fi
done

if [ -f "$cfg" ] && [ ! -L "$cfg" ]; then
  if [ "$(head -n1 "$cfg")" = "$src" ]; then
    rm "$cfg"; echo "removed:   $cfg"
    rmdir "$cfg_dir" 2>/dev/null || true
  else
    echo "left:      $cfg (names $(head -n1 "$cfg"), not this checkout)"
  fi
elif [ -e "$cfg" ] || [ -L "$cfg" ]; then
  echo "left:      $cfg (not a plain file)"
else
  echo "absent:    $cfg"
fi
