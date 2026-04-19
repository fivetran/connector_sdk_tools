#!/usr/bin/env bash
# Propagates canonical content into plugin directories.
# Run from repo root: bash scripts/sync-plugins.sh
# Idempotent — safe to re-run.
#
# Edit targets (canonical sources):
#   coding-agents/sdk-reference.md
#   coding-agents/workflows/{validator,generator,fixer}.md
#   coding-agents/claude-code/tools/*
#
# Generated files (DO NOT edit directly — edits will be overwritten):
#   coding-agents/claude-code/sdk-reference.md
#   coding-agents/claude-code/agents/connector-{validator,generator,fixer}.md
#   coding-agents/codex/sdk-reference.md
#   coding-agents/codex/tools/*

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

SDK_REF="coding-agents/sdk-reference.md"
WORKFLOWS_DIR="coding-agents/workflows"
CLAUDE_DIR="coding-agents/claude-code"
CODEX_DIR="coding-agents/codex"
TOOLS_SRC="$CLAUDE_DIR/tools"

# --- Helpers ---

banner() {
  # $1 = canonical source path (relative to repo root)
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

# Claude subagent frontmatter — prepended to each canonical workflow body.
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

assemble_claude_agent() {
  local role="$1"         # validator | generator | fixer
  local src="$WORKFLOWS_DIR/${role}.md"
  local dest="$CLAUDE_DIR/agents/connector-${role}.md"
  mkdir -p "$(dirname "$dest")"
  {
    claude_frontmatter "$role"
    echo ""
    banner "$src"
    cat "$src"
  } > "$dest"
  echo "  wrote $dest"
}

# --- Sync actions ---

echo "Syncing sdk-reference.md into plugins..."
copy_with_banner "$SDK_REF" "$CLAUDE_DIR/sdk-reference.md"
copy_with_banner "$SDK_REF" "$CODEX_DIR/sdk-reference.md"

echo "Assembling Claude subagent files..."
assemble_claude_agent validator
assemble_claude_agent generator
assemble_claude_agent fixer

echo "Copying tools into Codex plugin..."
mkdir -p "$CODEX_DIR/tools"
for f in "$TOOLS_SRC"/*; do
  dest="$CODEX_DIR/tools/$(basename "$f")"
  cp "$f" "$dest"
  echo "  wrote $dest"
done

echo "Done."
