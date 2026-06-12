#!/usr/bin/env bash
# Propagates canonical content into per-agent plugin/extension trees.
# Run from repo root: bash scripts/sync-plugins.sh
# Idempotent — safe to re-run.
#
# Canonical sources (edit these):
#   canonical/sdk-reference.md
#   canonical/native-connectors.md
#   canonical/workflows/{validator,generator,fixer}.md
#   canonical/skills/{build,test,deploy,evaluate,migrate-functions,migrate-meltano}-connector/SKILL.md
#   canonical/tools/*
#
# Generated files (DO NOT edit directly — edits will be overwritten):
#   claude-code/sdk-reference.md
#   claude-code/native-connectors.md
#   claude-code/agents/connector-{validator,generator,fixer}.md
#   claude-code/skills/{build,test,deploy,evaluate,migrate-functions,migrate-meltano}-connector/SKILL.md
#   claude-code/tools/*
#   codex/sdk-reference.md
#   codex/native-connectors.md
#   codex/skills/{build,test,deploy,evaluate,migrate-functions,migrate-meltano}-connector/SKILL.md
#   codex/workflows/{validator,generator,fixer}.md
#   codex/tools/*
#   sdk-reference.md                                         (Gemini)
#   native-connectors.md                                     (Gemini)
#   agents/connector-{validator,generator,fixer}.md          (Gemini)
#   skills/{build,test,deploy,evaluate,migrate-functions,migrate-meltano}-connector/SKILL.md            (Gemini)
#   tools/*                                                  (Gemini)
#   copilot/sdk-reference.md                                 (Copilot CLI)
#   copilot/native-connectors.md                             (Copilot CLI)
#   copilot/agents/connector-{validator,generator,fixer}.md  (Copilot CLI)
#   copilot/skills/{build,test,deploy,evaluate,migrate-functions,migrate-meltano}-connector/SKILL.md    (Copilot CLI)
#   copilot/tools/*                                          (Copilot CLI)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

CANONICAL="canonical"
SDK_REF="$CANONICAL/sdk-reference.md"
NATIVE_LIST="$CANONICAL/native-connectors.md"
WORKFLOWS_DIR="$CANONICAL/workflows"
SKILLS_DIR="$CANONICAL/skills"
TOOLS_SRC="$CANONICAL/tools"
CLAUDE_DIR="claude-code"
CODEX_DIR="codex"
GEMINI_DIR="."
COPILOT_DIR="copilot"
SKILLS=(build-connector test-connector deploy-connector evaluate-connector migrate-functions-connector migrate-meltano-connector)

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
tools: Read, Edit, WebFetch, Grep, Glob
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

# --- Sync actions ---

echo "Syncing sdk-reference.md..."
copy_with_banner "$SDK_REF" "$CLAUDE_DIR/sdk-reference.md"
copy_with_banner "$SDK_REF" "$CODEX_DIR/sdk-reference.md"
copy_with_banner "$SDK_REF" "$GEMINI_DIR/sdk-reference.md"
copy_with_banner "$SDK_REF" "$COPILOT_DIR/sdk-reference.md"

echo "Syncing native-connectors.md..."
copy_with_banner "$NATIVE_LIST" "$CLAUDE_DIR/native-connectors.md"
copy_with_banner "$NATIVE_LIST" "$CODEX_DIR/native-connectors.md"
copy_with_banner "$NATIVE_LIST" "$GEMINI_DIR/native-connectors.md"
copy_with_banner "$NATIVE_LIST" "$COPILOT_DIR/native-connectors.md"

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

echo "Done."
