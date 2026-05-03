#!/usr/bin/env bash
# =============================================================================
# sync_foundation_skills.sh — Make Superpowers default for OHO
# =============================================================================
#
# Symlinks the 9 always-on Foundation AddOn skills into <project>/.claude/skills/
# so the harness discovers them as project-scoped skills. Idempotent.
#
# Re-run after Foundation AddOn updates if new always-on skills are added.
#
# Usage:
#   bash scripts/sync_foundation_skills.sh
#
# =============================================================================
set -euo pipefail

FOUNDATION_ROOT="/Volumes/home/!! AI_Scripts_Automations_Projects/Projects_Repos/! Foundation_AddOn_Project"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILLS_DIR="$PROJECT_ROOT/.claude/skills"

# The always-on meta-layer per Foundation AddOn CLAUDE.md.
# All live under $FOUNDATION_ROOT/skills/core/<name>/SKILL.md
ALWAYS_ON_SKILLS=(
  anti-hallucination
  prompt-amplifier
  cognitive-excellence
  context-guardian
  efficiency-engine
  secure-by-design
  solution-architect-engine
  verification-before-completion
  session-optimizer
)

mkdir -p "$SKILLS_DIR"

if [[ ! -d "$FOUNDATION_ROOT/skills/core" ]]; then
  echo "ERROR: Foundation AddOn not found at $FOUNDATION_ROOT" >&2
  exit 1
fi

linked=0
skipped=0
missing=0

for skill in "${ALWAYS_ON_SKILLS[@]}"; do
  src="$FOUNDATION_ROOT/skills/core/$skill"
  dst="$SKILLS_DIR/$skill"

  if [[ ! -f "$src/SKILL.md" ]]; then
    # verification-before-completion sometimes lives under a different category
    alt=$(find "$FOUNDATION_ROOT/skills" -maxdepth 3 -type d -name "$skill" 2>/dev/null | head -1)
    if [[ -n "$alt" && -f "$alt/SKILL.md" ]]; then
      src="$alt"
    else
      echo "[MISSING] $skill — no SKILL.md found under $FOUNDATION_ROOT/skills/"
      missing=$((missing + 1))
      continue
    fi
  fi

  if [[ -L "$dst" ]]; then
    if [[ "$(readlink "$dst")" == "$src" ]]; then
      skipped=$((skipped + 1))
      continue
    fi
    rm "$dst"
  elif [[ -e "$dst" ]]; then
    echo "[CONFLICT] $dst exists and is not our symlink — leaving alone"
    continue
  fi

  ln -s "$src" "$dst"
  linked=$((linked + 1))
done

echo
echo "Sync complete: linked=$linked  already-current=$skipped  missing=$missing"
echo "Project skills dir: $SKILLS_DIR"
ls -la "$SKILLS_DIR"
