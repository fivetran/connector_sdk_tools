# Fivetran Connector Builder — Codex CLI Plugin

Build, test, fix, and deploy Fivetran connectors with AI assistance, directly in Codex CLI.

## Prerequisites

- Python 3.10-3.14
- [Codex CLI](https://github.com/openai/codex) installed
- [Fivetran Connector SDK](https://pypi.org/project/fivetran-connector-sdk/) — `pip install fivetran-connector-sdk`
- A Fivetran account (https://fivetran.com)

## Installation

See the [top-level README](../README.md#install) for the full install matrix. Quick path:

1. Enable the plugins feature in `~/.codex/config.toml`:
   ```toml
   [features]
   plugins = true
   ```

2. Add the marketplace and install:
   ```bash
   codex plugin marketplace add fivetran/connector_sdk_tools
   codex plugin add fivetran-connector-sdk@fivetran-connector-sdk-ai
   ```

3. Enable the plugin in `~/.codex/config.toml`:
   ```toml
   [plugins."fivetran-connector-sdk@fivetran-connector-sdk-ai"]
   enabled = true
   ```

4. Install tool dependencies:

   macOS/Linux:
   ```bash
   python -m pip install -r /path/to/codex/tools/requirements.txt
   ```

   Windows PowerShell:
   ```powershell
   python -m pip install -r "C:\path\to\codex\tools\requirements.txt"
   ```

This dependency install is temporary. Until secure configuration entry is available directly in the Fivetran Connector SDK CLI, the plugin uses `tools/enter_configuration.py` to encrypt `configuration.json`.

On first run, `enter_configuration.py` creates a local encryption secret under your user profile (`~/.fivetran/csdk_master_secret` on macOS/Linux, `%USERPROFILE%\.fivetran\csdk_master_secret` on Windows). It uses that secret to add encrypted credential values to the top-level `encrypted` field in `configuration.json`; the AI does not see the secret or plaintext credentials. The original placeholder fields remain as the recoverable baseline.

Only `enter_configuration.py` creates the secret. The test and deploy tools require the existing secret so they can decrypt the `encrypted` field. To start credential entry over, delete the `encrypted` field from `configuration.json` and run `enter_configuration.py` again.

## Usage

Skills appear in the `$` mention popup:

- `$build_connector` — Research an API and generate a complete connector
- `$test_connector` — Run and validate your connector locally
- `$deploy_connector` — Package and deploy to Fivetran

To fix or modify an existing connector, describe the problem or change in natural language — the plugin guides the agent through the fixer workflow (classification → pattern research → targeted fix).

## What's Included

| Component | Description |
|-----------|-------------|
| `skills/build-connector/` | Full generation workflow (research → generate → test → auto-fix) |
| `skills/test-connector/` | Run and validate connector tests |
| `skills/deploy-connector/` | Package and deploy to Fivetran |
| `workflows/fixer.md` | Canonical fix workflow (applied when user reports an error or asks for a change) |
| `tools/enter_configuration.py` | Enter and encrypt API credentials |
| `tools/run_connector.py` | Run connector with encrypted config (decrypts via named pipe) |
| `tools/deploy_connector.py` | Deploy connector with auto-discovered destination |

## Telemetry

This plugin collects anonymous usage data (skill name, plugin name and version, model, status, session ID, timestamp) to help improve the product. No prompts, code, or personal information are collected. To opt out, add to your shell profile:

```bash
export FIVETRAN_TELEMETRY_DISABLED=1
```

## Known Parity Gaps vs. Claude Code Plugin

- **Subagents**: Codex has no subagent concept. The validator/generator/fixer workflows are inlined in the relevant SKILL.md files instead of running as isolated subagents.
