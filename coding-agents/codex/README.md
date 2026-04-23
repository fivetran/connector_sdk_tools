# Fivetran Connector Builder — Codex CLI Plugin

Build, test, fix, and deploy Fivetran connectors with AI assistance, directly in Codex CLI.

## Prerequisites

- Python 3.10-3.14
- [Codex CLI](https://github.com/openai/codex) installed
- [Fivetran Connector SDK](https://pypi.org/project/fivetran-connector-sdk/) — `pip install fivetran-connector-sdk`
- A Fivetran account (https://fivetran.com)

## Installation

### Automatic (coming soon)

```bash
fivetran ai setup --agent codex
```

### Install script

```bash
bash scripts/install-codex.sh
```

Prints step-by-step instructions for installing the plugin via Codex's native marketplace flow and enabling the plugins feature flag.

### Manual

1. Enable the plugins feature in `~/.codex/config.toml`:
   ```toml
   [features]
   plugins = true
   ```

2. Add this repo as a Codex marketplace (Codex requires a local path):
   ```bash
   cd /path/to/fivetran_csdk_tools
   codex plugin marketplace add .
   ```

3. Install the plugin:
   ```bash
   codex plugin install fivetran-csdk@fivetran-csdk-tools
   ```

4. Enable the plugin:
   ```toml
   [plugins."fivetran-csdk@fivetran-csdk-tools"]
   enabled = true
   ```

5. Install tool dependencies:
   ```bash
   pip install -r coding-agents/codex/tools/requirements.txt
   ```

## Fallback: Agent Instructions Without Plugin

If you prefer not to install the plugin, copy `../AGENTS.md` into your connector project root. Codex will read it automatically but you'll lose the skills, secure credential handling, and CSDK-specific workflows.

```bash
cp coding-agents/AGENTS.md /path/to/my-connector/AGENTS.md
```

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

## Known Parity Gaps vs. Claude Code Plugin

- **Subagents**: Codex has no subagent concept. The validator/generator/fixer workflows are inlined in the relevant SKILL.md files instead of running as isolated subagents.
- **Hooks**: Codex has no hooks. Claude's post-edit reminder to run `/test-connector` has no Codex equivalent.
