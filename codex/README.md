# Fivetran Connector Builder — Codex CLI Plugin

Build, test, fix, and deploy Fivetran connectors with AI assistance, directly in Codex CLI.

## Prerequisites

- Python 3.11-3.15
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

   To update:
   ```bash
   codex plugin marketplace upgrade fivetran-connector-sdk-ai
   ```

3. Enable the plugin in `~/.codex/config.toml`:
   ```toml
   [plugins."fivetran-connector-sdk@fivetran-connector-sdk-ai"]
   enabled = true
   ```

4. If using encrypted configuration, install tool dependencies:

   macOS/Linux:
   ```bash
   python -m pip install -r /path/to/codex/tools/requirements.txt
   ```

   Windows PowerShell:
   ```powershell
   python -m pip install -r "C:\path\to\codex\tools\requirements.txt"
   ```

## Configuration

Reuse existing configuration and collect only missing values. Use the project's
`fivetran configuration` setup form when available, or ordinary `configuration.json`
otherwise. Keep secrets out of chat. See
[Configuration entry](sdk-reference.md#configuration-entry) for the shared workflow
and the [optional encryption documentation](../README.md#optional-encrypted-configuration)
if you use encrypted fields.

## Usage

Skills appear in the `$` mention popup:

- `$build_connector` — Research an API and generate a complete connector
- `$test_connector` — Run and validate your connector locally
- `$deploy_connector` — Package and deploy to Fivetran
- `$evaluate_connector` — Code review and quality report
- `$submit_to_community_catalog` — Submit a Connector SDK example or connector contribution in a pull request
- `$migrate_functions_connector` — Migrate a Fivetran Functions connector to Connector SDK
- `$migrate_meltano_connector` — Migrate a Meltano extractor or Singer tap to Connector SDK
- `$migrate_airbyte_connector` — Migrate an Airbyte source connector to Connector SDK

To fix or modify an existing connector, describe the problem or change in natural language — the plugin guides the agent through the fixer workflow (classification → pattern research → targeted fix).

## What's Included

| Component | Description |
|-----------|-------------|
| `skills/build-connector/` | Full generation workflow (research → generate → test → auto-fix) |
| `skills/test-connector/` | Run and validate connector tests |
| `skills/deploy-connector/` | Package and deploy to Fivetran |
| `skills/evaluate-connector/` | Static code review and scored report |
| `skills/submit-to-community-catalog/` | Submit a Connector SDK example or connector contribution in a pull request |
| `skills/migrate-functions-connector/` | Migrate Fivetran Functions connectors to Connector SDK |
| `skills/migrate-meltano-connector/` | Migrate Meltano extractors or Singer taps to Connector SDK |
| `skills/migrate-airbyte-connector/` | Migrate Airbyte source connectors to Connector SDK |
| `workflows/fixer.md` | Canonical fix workflow (applied when user reports an error or asks for a change) |
| `tools/enter_configuration.py` | Optional local encryption of configuration values |
| `tools/run_connector.py` | Run connector with runtime config via named pipe |
| `tools/deploy_connector.py` | Redeploy with `--connection-id`, or deploy to an explicit `--destination` (with discovery as a fallback) |

## Telemetry

This plugin collects **anonymous usage data** to help improve the product. When one of its skills (build, test, deploy, evaluate, or submit-to-community-catalog) runs, it sends one small event with: skill name, plugin name and version, model, status (`started`, `ok`, or `fail`), session ID, and timestamp. No prompts, code, file contents, credentials, or personal information are collected.

**One-time notice.** The first time a Fivetran skill is used, the plugin shows a short notice and sends no event on that run, so you can opt out first.

**Opt out.** Set either variable in your shell profile (`~/.zshrc`, `~/.bashrc`, etc.):

```bash
export DO_NOT_TRACK=1                  # "1" or "true"
export FIVETRAN_TELEMETRY_DISABLED=1
```

**What the hook sees.** Codex has no event for skill commands only, so the hook receives every prompt. The script reads only the leading `/` or `$` token and discards the rest.

Learn more: [Data Use and Telemetry](https://fivetran.com/docs/security-and-privacy/telemetry).

## Known Parity Gaps vs. Claude Code Plugin

- **Subagents**: Codex has no subagent concept. The validator/generator/fixer workflows are inlined in the relevant SKILL.md files instead of running as isolated subagents.
