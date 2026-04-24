#!/usr/bin/env bash
# Install the Fivetran CSDK plugin for OpenAI Codex CLI.
# Uses Codex's native marketplace and plugin install flow.
# Edits the user's Codex config to enable the plugins feature.
#
# Usage: bash scripts/install-codex.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CODEX_CONFIG="${CODEX_HOME:-$HOME/.codex}/config.toml"

cat <<EOF
Installing the Fivetran CSDK plugin for Codex CLI.

Codex requires the plugins feature to be enabled in user config.
Your config: $CODEX_CONFIG

Steps to complete manually:

1. Enable the plugins feature in $CODEX_CONFIG:

     [features]
     plugins = true

2. Add this repo as a Codex marketplace:

     cd $REPO_ROOT
     codex plugin marketplace add .

   (Codex requires a local path; it does not accept remote URLs directly.)

3. Install the plugin:

     codex plugin install fivetran-connector-sdk@fivetran-connector-sdk-tools

4. Enable the plugin in $CODEX_CONFIG:

     [plugins."fivetran-connector-sdk@fivetran-connector-sdk-tools"]
     enabled = true

5. Install the tool dependencies:

     pip install -r $REPO_ROOT/coding-agents/codex/tools/requirements.txt

6. Restart Codex and verify the plugin appears in the \$ mention popup (try \$build_connector).
EOF
