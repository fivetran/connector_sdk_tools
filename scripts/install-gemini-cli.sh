#!/usr/bin/env bash
# Install Fivetran CSDK agent instructions for Gemini CLI.
# Copies AGENTS.md into the target connector project as GEMINI.md.
#
# Usage: bash scripts/install-gemini-cli.sh <target-project-dir>

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$REPO_ROOT/coding-agents/AGENTS.md"

if [ $# -lt 1 ]; then
  echo "Usage: bash scripts/install-gemini-cli.sh <target-project-dir>" >&2
  exit 1
fi

TARGET="$1"

if [ ! -d "$TARGET" ]; then
  echo "Error: target directory does not exist: $TARGET" >&2
  exit 1
fi

cp "$SRC" "$TARGET/GEMINI.md"
echo "Installed: $TARGET/GEMINI.md"
echo "Gemini CLI will pick up these instructions automatically."
