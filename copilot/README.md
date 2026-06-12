# Fivetran Connector Builder — GitHub Copilot CLI Plugin

Build, test, fix, and deploy Fivetran connectors with AI assistance, directly in GitHub Copilot CLI.

## Prerequisites

- Python 3.10-3.14
- [GitHub Copilot CLI](https://docs.github.com/en/copilot/github-copilot-in-the-cli) installed (`copilot` v1.0.57+)
- [Fivetran Connector SDK](https://pypi.org/project/fivetran-connector-sdk/) — `pip install fivetran-connector-sdk`
- A Fivetran account (https://fivetran.com)

## Installation

See the [top-level README](../README.md#install) for the full install matrix. Quick path:

```bash
copilot plugin marketplace add fivetran/connector_sdk_tools
copilot plugin install fivetran-connector-sdk@fivetran-connector-sdk-ai
```

Install the tool dependencies:

macOS/Linux:
```bash
python -m pip install -r /path/to/copilot/tools/requirements.txt
```

Windows PowerShell:
```powershell
python -m pip install -r "C:\path\to\copilot\tools\requirements.txt"
```

This dependency install is temporary. Until secure configuration entry is available directly in the Fivetran Connector SDK CLI, the plugin uses `tools/enter_configuration.py` to encrypt configuration values in `configuration.json`.

On first run, `enter_configuration.py` creates a local encryption secret under your user profile (`~/.fivetran/csdk_master_secret` on macOS/Linux, `%USERPROFILE%\.fivetran\csdk_master_secret` on Windows). It uses that secret to write inline `ENCRYPTED:v1:<key_id>:local-fernet:` values for every field. The AI does not see plaintext configuration values.

Only `enter_configuration.py` creates the secret. The test and deploy tools require the existing secret to decrypt configuration values at runtime. To start configuration entry over, run `enter_configuration.py` again.

## Usage

Commands appear as slash commands:

- `/fivetran-connector-sdk:build-connector` — Research an API and generate a complete connector
- `/fivetran-connector-sdk:test-connector` — Run and validate your connector locally
- `/fivetran-connector-sdk:deploy-connector` — Package and deploy to Fivetran
- `/fivetran-connector-sdk:evaluate-connector` — Code review and quality report

To fix or modify an existing connector, describe the problem or change in natural language — the plugin routes to the `connector-fixer` agent automatically.

## What's Included

| Component | Description |
|-----------|-------------|
| `commands/build-connector.md` | Full generation workflow (research → generate → test → auto-fix) |
| `commands/test-connector.md` | Run and validate connector tests |
| `commands/deploy-connector.md` | Package and deploy to Fivetran |
| `commands/evaluate-connector.md` | Static code review and scored report |
| `agents/connector-validator.md` | Agent for API research and requirements gathering |
| `agents/connector-generator.md` | Agent for generating connector code |
| `agents/connector-fixer.md` | Agent for diagnosing and fixing errors |
| `tools/enter_configuration.py` | Enter and encrypt API credentials |
| `tools/run_connector.py` | Run connector with encrypted config (decrypts via named pipe) |
| `tools/deploy_connector.py` | Deploy connector with auto-discovered destination |
