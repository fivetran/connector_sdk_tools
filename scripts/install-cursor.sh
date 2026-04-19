#!/usr/bin/env bash
# Install Fivetran CSDK agent instructions for Cursor.
# Copies AGENTS.md into the target connector project.
#
# Usage: bash scripts/install-cursor.sh <target-project-dir>

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$REPO_ROOT/coding-agents/AGENTS.md"

if [ $# -lt 1 ]; then
  echo "Usage: bash scripts/install-cursor.sh <target-project-dir>" >&2
  exit 1
fi

TARGET="$1"

if [ ! -d "$TARGET" ]; then
  echo "Error: target directory does not exist: $TARGET" >&2
  exit 1
fi

cp "$SRC" "$TARGET/AGENTS.md"
echo "Installed: $TARGET/AGENTS.md"
echo "Cursor will pick up these instructions automatically."
