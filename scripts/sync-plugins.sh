#!/usr/bin/env bash
# Propagates canonical content into per-agent plugin/extension trees.
# Run from repo root: bash scripts/sync-plugins.sh
# Idempotent — safe to re-run.
#
# Canonical sources (edit these):
#   canonical/sdk-reference.md
#   canonical/workflows/{validator,generator,fixer}.md
#   canonical/skills/{build,test,deploy,evaluate,migrate-functions,migrate-meltano,migrate-airbyte}-connector/SKILL.md
#   canonical/skills/connector-sdk-submit/SKILL.md
#   canonical/tools/*
#   canonical/hooks/log-skill-use.sh
#
# Generated files (DO NOT edit directly — edits will be overwritten):
#   claude-code/sdk-reference.md
#   claude-code/agents/connector-{validator,generator,fixer}.md
#   claude-code/skills/{build,test,deploy,evaluate,migrate-functions,migrate-meltano,migrate-airbyte}-connector/SKILL.md
#   claude-code/skills/connector-sdk-submit/SKILL.md
#   claude-code/tools/*
#   claude-code/hooks/log-skill-use.sh
#   codex/sdk-reference.md
#   codex/native-connectors.md
#   codex/skills/{build,test,deploy,evaluate,migrate-functions,migrate-meltano,migrate-airbyte}-connector/SKILL.md
#   codex/skills/connector-sdk-submit/SKILL.md
#   codex/workflows/{validator,generator,fixer}.md
#   codex/tools/*
#   codex/hooks/log-skill-use.sh
#   sdk-reference.md                                         (Gemini)
#   agents/connector-{validator,generator,fixer}.md          (Gemini)
#   skills/{build,test,deploy,evaluate,migrate-functions,migrate-meltano,migrate-airbyte}-connector/SKILL.md            (Gemini)
#   skills/connector-sdk-submit/SKILL.md                                                                            (Gemini)
#   tools/*                                                  (Gemini)
#   hooks/log-skill-use.sh                                   (Gemini)
#   copilot/sdk-reference.md                                 (Copilot CLI)
#   copilot/agents/connector-{validator,generator,fixer}.md  (Copilot CLI)
#   copilot/skills/{build,test,deploy,evaluate,migrate-functions,migrate-meltano,migrate-airbyte}-connector/SKILL.md    (Copilot CLI)
#   copilot/skills/connector-sdk-submit/SKILL.md                                                                      (Copilot CLI)
#   copilot/tools/*                                          (Copilot CLI)

set -euo pipefail

# --- Argument parsing ---
# --bump   Increment the plugin version. Omit for routine content syncs (e.g.
#          the pre-commit hook) so the script stays idempotent: running it on
#          an already-synced repo produces no diff.
BUMP_VERSION=false
for arg in "$@"; do
  case "$arg" in
    --bump) BUMP_VERSION=true ;;
    *) echo "Unknown argument: $arg" >&2; exit 1 ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# --- Version management ---
# Format: YYYY.M.D.N  (e.g. 2026.6.25.1)
# N auto-increments when multiple releases happen on the same calendar day.
# Version is only written when --bump is passed; otherwise manifests are left
# untouched so the pre-commit hook never creates a spurious diff.

_today_prefix() {
  # Returns YYYY.M.D with no zero-padding (e.g. 2026.6.25). Uses UTC so the
  # version is identical across timezones.
  local y m d
  y=$(date -u "+%Y")
  m=$(date -u "+%-m" 2>/dev/null || date -u "+%m" | sed 's/^0//')
  d=$(date -u "+%-d" 2>/dev/null || date -u "+%d" | sed 's/^0//')
  echo "${y}.${m}.${d}"
}

compute_version() {
  local prefix
  prefix="$(_today_prefix)"

  # Read the current version from the Claude plugin manifest (source of truth).
  local current_version=""
  local manifest="claude-code/.claude-plugin/plugin.json"
  if [[ -f "$manifest" ]]; then
    current_version=$(grep '"version"' "$manifest" | sed 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/')
  fi

  local iteration=1
  # If the current version already has today's date prefix, bump the iteration.
  if [[ "$current_version" == "$prefix."* ]]; then
    local current_iteration="${current_version##*.}"
    iteration=$(( current_iteration + 1 ))
  fi

  echo "${prefix}.${iteration}"
}

update_version_in_file() {
  local file="$1"
  local version="$2"
  # Replace all "version": "..." occurrences in-place.
  sed -i.bak "s/\"version\"[[:space:]]*:[[:space:]]*\"[^\"]*\"/\"version\": \"${version}\"/g" "$file"
  rm -f "${file}.bak"
  echo "  updated version in $file"
}

if [[ "$BUMP_VERSION" == true ]]; then
  NEW_VERSION="$(compute_version)"
  echo "Bumping plugin version to $NEW_VERSION..."
  update_version_in_file "claude-code/.claude-plugin/plugin.json" "$NEW_VERSION"
  update_version_in_file "codex/.codex-plugin/plugin.json" "$NEW_VERSION"
  update_version_in_file "gemini-extension.json" "$NEW_VERSION"
  update_version_in_file ".github/plugin/marketplace.json" "$NEW_VERSION"
else
  echo "Skipping version bump (pass --bump to increment the version)."
fi

CANONICAL="canonical"
SDK_REF="$CANONICAL/sdk-reference.md"
WORKFLOWS_DIR="$CANONICAL/workflows"
SKILLS_DIR="$CANONICAL/skills"
TOOLS_SRC="$CANONICAL/tools"
HOOKS_SRC="$CANONICAL/hooks"
CLAUDE_DIR="claude-code"
CODEX_DIR="codex"
GEMINI_DIR="."
COPILOT_DIR="copilot"
SKILLS=(build-connector test-connector deploy-connector evaluate-connector connector-sdk-submit migrate-functions-connector migrate-meltano-connector migrate-airbyte-connector)

# --- Helpers ---

banner() {
  cat <<EOF
<!--
  GENERATED FILE — DO NOT EDIT.
  Canonical source: $1
  Regenerate with: bash scripts/sync-plugins.sh
-->

EOF
}

copy_with_banner() {
  local src="$1"
  local dest="$2"
  mkdir -p "$(dirname "$dest")"
  {
    banner "$src"
    cat "$src"
  } > "$dest"
  echo "  wrote $dest"
}

claude_frontmatter() {
  case "$1" in
    validator)
      cat <<'EOF'
---
name: connector-validator
description: Research API documentation and gather complete requirements for building a Fivetran connector. Use when researching data sources before code generation.
tools: Read, WebFetch, Glob, Grep
model: sonnet
maxTurns: 15
---
EOF
      ;;
    generator)
      cat <<'EOF'
---
name: connector-generator
description: Generate Fivetran connector code from a validated specification. Use after requirements have been gathered.
tools: Read, Write, Edit, WebFetch
model: sonnet
maxTurns: 20
permissionMode: acceptEdits
---
EOF
      ;;
    fixer)
      cat <<'EOF'
---
name: connector-fixer
description: Debug and fix errors in a Fivetran connector. Use when tests fail or the user reports connector issues.
tools: Read, Edit, Bash, WebFetch, Grep, Glob
model: sonnet
maxTurns: 15
permissionMode: acceptEdits
---
EOF
      ;;
    *)
      echo "Unknown role: $1" >&2
      exit 1
      ;;
  esac
}

gemini_frontmatter() {
  case "$1" in
    validator)
      cat <<'EOF'
---
name: connector-validator
description: Research API documentation and gather complete requirements for building a Fivetran connector. Use when researching data sources before code generation.
---
EOF
      ;;
    generator)
      cat <<'EOF'
---
name: connector-generator
description: Generate Fivetran connector code from a validated specification. Use after requirements have been gathered.
---
EOF
      ;;
    fixer)
      cat <<'EOF'
---
name: connector-fixer
description: Debug and fix errors in a Fivetran connector. Use when tests fail or the user reports connector issues.
---
EOF
      ;;
    *)
      echo "Unknown role: $1" >&2
      exit 1
      ;;
  esac
}

copilot_frontmatter() {
  case "$1" in
    validator)
      cat <<'EOF'
---
name: connector-validator
description: Research API documentation and gather complete requirements for building a Fivetran connector. Use when researching data sources before code generation.
---
EOF
      ;;
    generator)
      cat <<'EOF'
---
name: connector-generator
description: Generate Fivetran connector code from a validated specification. Use after requirements have been gathered.
---
EOF
      ;;
    fixer)
      cat <<'EOF'
---
name: connector-fixer
description: Debug and fix errors in a Fivetran connector. Use when tests fail or the user reports connector issues.
---
EOF
      ;;
    *)
      echo "Unknown role: $1" >&2
      exit 1
      ;;
  esac
}

assemble_agent() {
  local role="$1"        # validator | generator | fixer
  local target="$2"      # claude | gemini | copilot
  local src="$WORKFLOWS_DIR/${role}.md"
  local dest
  case "$target" in
    claude)  dest="$CLAUDE_DIR/agents/connector-${role}.md" ;;
    gemini)  dest="$GEMINI_DIR/agents/connector-${role}.md" ;;
    copilot) dest="$COPILOT_DIR/agents/connector-${role}.md" ;;
    *) echo "Unknown target: $target" >&2; exit 1 ;;
  esac
  mkdir -p "$(dirname "$dest")"
  {
    "${target}_frontmatter" "$role"
    echo ""
    banner "$src"
    cat "$src"
  } > "$dest"
  echo "  wrote $dest"
}

# Copy a canonical SKILL.md to a plugin dir, inserting a "GENERATED" banner
# after the frontmatter block (so frontmatter parsers still see it at line 1).
copy_skill_with_banner() {
  local src="$1"
  local dest="$2"
  mkdir -p "$(dirname "$dest")"
  awk -v src="$src" '
    BEGIN { delim=0 }
    /^---$/ {
      print
      delim++
      if (delim == 2) {
        print ""
        print "<!--"
        print "  GENERATED FILE — DO NOT EDIT."
        print "  Canonical source: " src
        print "  Regenerate with: bash scripts/sync-plugins.sh"
        print "-->"
      }
      next
    }
    { print }
  ' "$src" > "$dest"
  echo "  wrote $dest"
}

copy_tools() {
  local dest_dir="$1"
  mkdir -p "$dest_dir"
  for f in "$TOOLS_SRC"/*; do
    [[ -f "$f" ]] || continue
    cp "$f" "$dest_dir/$(basename "$f")"
    echo "  wrote $dest_dir/$(basename "$f")"
  done
}

copy_hooks() {
  local dest_dir="$1"
  mkdir -p "$dest_dir"
  for f in "$HOOKS_SRC"/*; do
    [[ -f "$f" ]] || continue
    cp "$f" "$dest_dir/$(basename "$f")"
    chmod +x "$dest_dir/$(basename "$f")"
    echo "  wrote $dest_dir/$(basename "$f")"
  done
}

# --- Sync actions ---

echo "Syncing sdk-reference.md..."
copy_with_banner "$SDK_REF" "$CLAUDE_DIR/sdk-reference.md"
copy_with_banner "$SDK_REF" "$CODEX_DIR/sdk-reference.md"
copy_with_banner "$SDK_REF" "$GEMINI_DIR/sdk-reference.md"
copy_with_banner "$SDK_REF" "$COPILOT_DIR/sdk-reference.md"

echo "Assembling Claude subagent files..."
for role in validator generator fixer; do
  assemble_agent "$role" claude
done

echo "Assembling Gemini agent files..."
for role in validator generator fixer; do
  assemble_agent "$role" gemini
done

echo "Assembling Copilot agent files..."
for role in validator generator fixer; do
  assemble_agent "$role" copilot
done

echo "Copying workflow files into Codex plugin..."
mkdir -p "$CODEX_DIR/workflows"
for role in validator generator fixer; do
  copy_with_banner "$WORKFLOWS_DIR/${role}.md" "$CODEX_DIR/workflows/${role}.md"
done

echo "Syncing canonical skills..."
for skill in "${SKILLS[@]}"; do
  src="$SKILLS_DIR/${skill}/SKILL.md"
  copy_skill_with_banner "$src" "$CLAUDE_DIR/skills/${skill}/SKILL.md"
  copy_skill_with_banner "$src" "$CODEX_DIR/skills/${skill}/SKILL.md"
  copy_skill_with_banner "$src" "$GEMINI_DIR/skills/${skill}/SKILL.md"
  copy_skill_with_banner "$src" "$COPILOT_DIR/skills/${skill}/SKILL.md"
done

echo "Copying tools..."
copy_tools "$CLAUDE_DIR/tools"
copy_tools "$CODEX_DIR/tools"
copy_tools "$GEMINI_DIR/tools"
copy_tools "$COPILOT_DIR/tools"

echo "Copying hooks..."
copy_hooks "$CLAUDE_DIR/hooks"
copy_hooks "$CODEX_DIR/hooks"
copy_hooks "$GEMINI_DIR/hooks"
# Copilot CLI has no lifecycle hook system (no UserPromptSubmit/PostToolUse events);
# it uses commands/ markdown files only, so hooks are not synced there.

# --- AI build marker ---
# Canonical sources hold {{PLUGIN_NAME}}, {{PLUGIN_AGENT}} and {{PLUGIN_VERSION}}
# placeholders (the "Built using Connector SDK AI Plugin" header). Each generated
# tree gets them filled from its own manifest, so the version always matches the
# release that produced the connector.
manifest_field() {
  # manifest_field <key> <file>: first "<key>": "<value>" in the file.
  grep -m1 "\"$1\"" "$2" | sed "s/.*\"$1\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/"
}

fill_plugin_markers() {
  # fill_plugin_markers <agent> <manifest> <path>...
  # The plugin name is fixed: marketplace manifests also carry a "name" that is
  # not the plugin name, so it is not read from the file.
  local agent="$1" manifest="$2"
  shift 2
  local name="fivetran-connector-sdk" version f
  version="$(manifest_field version "$manifest")"
  for path in "$@"; do
    [[ -e "$path" ]] || continue
    while IFS= read -r f; do
      sed -i.bak \
        -e "s/{{PLUGIN_NAME}}/${name}/g" \
        -e "s/{{PLUGIN_AGENT}}/${agent}/g" \
        -e "s/{{PLUGIN_VERSION}}/${version}/g" "$f"
      rm -f "${f}.bak"
    done < <(grep -rl '{{PLUGIN_' "$path" 2>/dev/null || true)
  done
}

echo "Filling AI build marker placeholders..."
fill_plugin_markers claude-code "$CLAUDE_DIR/.claude-plugin/plugin.json" "$CLAUDE_DIR"
fill_plugin_markers codex "$CODEX_DIR/.codex-plugin/plugin.json" "$CODEX_DIR"
fill_plugin_markers copilot ".github/plugin/marketplace.json" "$COPILOT_DIR"
# Gemini tree is the repo root, so only its generated paths are scanned.
fill_plugin_markers gemini gemini-extension.json skills agents tools hooks sdk-reference.md

echo "Done."
