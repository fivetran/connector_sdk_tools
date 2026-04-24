#!/usr/bin/env bash
# Install the Fivetran CSDK plugin for Claude Code.
# Uses Claude Code's native marketplace and plugin install flow.
#
# Usage: bash scripts/install-claude-code.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cat <<EOF
To install the Fivetran Connector SDK plugin for Claude Code, run these in your Claude Code session:

  /plugin marketplace add $REPO_ROOT
  /plugin install fivetran-connector-sdk@fivetran-connector-sdk-tools

Or, if you've pushed this repo to GitHub (fivetran/fivetran_csdk_tools):

  /plugin marketplace add fivetran/fivetran_csdk_tools
  /plugin install fivetran-connector-sdk@fivetran-connector-sdk-tools

After install, install the tool dependencies:

  pip install -r $REPO_ROOT/coding-agents/claude-code/tools/requirements.txt

Verify:

  /plugin marketplace list
EOF
