# Fivetran Connector Builder — Codex CLI Plugin

Build, test, fix, and deploy Fivetran connectors with AI assistance, directly in Codex CLI.

## Prerequisites

- [Codex CLI](https://github.com/openai/codex) installed
- Python 3.10-3.14
- [Fivetran Connector SDK](https://pypi.org/project/fivetran-connector-sdk/)

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
- `$fix_connector` — Diagnose and fix errors
- `$deploy_connector` — Package and deploy to Fivetran

## What's Included

| Component | Description |
|-----------|-------------|
| `skills/build-connector/` | Full generation workflow (research → generate → test → fix) |
| `skills/test-connector/` | Run and validate connector tests |
| `skills/fix-connector/` | Diagnose and fix connector errors |
| `skills/deploy-connector/` | Package and deploy to Fivetran |
| `tools/enter_configuration.py` | Enter and encrypt API credentials |
| `tools/run_connector.py` | Run connector with encrypted config (decrypts via named pipe) |
| `tools/deploy_connector.py` | Deploy connector with encrypted config |

## Known Parity Gaps vs. Claude Code Plugin

- **Subagents**: Codex has no subagent concept. The validator/generator/fixer workflows are inlined in the relevant SKILL.md files instead of running as isolated subagents.
- **Hooks**: Codex has no hooks. Claude's post-edit reminder to run `/test-connector` has no Codex equivalent.
