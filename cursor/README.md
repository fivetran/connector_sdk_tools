# Fivetran Connector SDK — Cursor Plugin

AI-assisted workflows for building, testing, evaluating, migrating, and deploying [Fivetran Connector SDK](https://fivetran.com/docs/connector-sdk) connectors in Cursor CLI.

## Prerequisites

- Python 3.10–3.14
- [Cursor CLI](https://cursor.com/docs/cli/overview)
- [Fivetran Connector SDK](https://pypi.org/project/fivetran-connector-sdk/) — `pip install fivetran-connector-sdk`
- A [Fivetran account](https://fivetran.com/)

## Installation

1. Register the Fivetran plugin marketplace:

   ```bash
   agent plugin marketplace add https://github.com/fivetran/connector_sdk_tools
   ```

2. Run `agent` to start an interactive Cursor CLI session.
3. Enter `/plugin` and open the Marketplace section.
4. Find **Fivetran Connector SDK**, select it, and choose user or project scope.

Cursor does not currently provide a non-interactive `agent plugin install` command, so `fivetran init` registers the marketplace and directs you to complete installation interactively.

To refresh the marketplace for an updated plugin version:

```bash
agent plugin marketplace update https://github.com/fivetran/connector_sdk_tools
```

Then run `agent` and enter `/plugin` to apply the available plugin update.

## Configuration

Reuse existing configuration values and collect only missing values. Use the project's `fivetran configuration` setup form when available, or ordinary `configuration.json` otherwise. Keep secrets out of chat and version control. See [Configuration entry](sdk-reference.md#configuration-entry) for the shared workflow and the [optional encrypted configuration documentation](../README.md#optional-encrypted-configuration) if you use encrypted fields.

## Usage

| Skill | Purpose |
|---|---|
| `build-connector` | Research an API and generate a new connector |
| `test-connector` | Run and validate an existing connector locally |
| `deploy-connector` | Deploy a connector to Fivetran |
| `evaluate-connector` | Review connector correctness and quality |
| `connector-sdk-submit` | Prepare and submit a Connector SDK contribution |
| `migrate-functions-connector` | Migrate a Fivetran Functions connector |
| `migrate-meltano-connector` | Migrate a Meltano extractor or Singer tap |
| `migrate-airbyte-connector` | Migrate an Airbyte source connector |

Open Cursor's skill menu or enter `/skill-name` in chat to invoke a skill.

To fix or modify an existing connector, describe the problem or requested change in natural language. The plugin can delegate the task to the `connector-fixer` agent.

## Specialized agents

The plugin includes agents for API validation, connector generation, and connector repair. The workflow files remain available as a fallback for environments where a skill cannot delegate to a specialized agent.

## What's Included

| Component | Description |
|---|---|
| `skills/build-connector/` | Full generation workflow from research through local testing and repair |
| `skills/test-connector/` | Run and validate a connector locally |
| `skills/deploy-connector/` | Package and deploy a connector to Fivetran |
| `skills/evaluate-connector/` | Static code review and scored quality report |
| `skills/connector-sdk-submit/` | Prepare a Connector SDK example or connector contribution for submission |
| `skills/migrate-functions-connector/` | Migrate a Fivetran Functions connector |
| `skills/migrate-meltano-connector/` | Migrate a Meltano extractor or Singer tap |
| `skills/migrate-airbyte-connector/` | Migrate an Airbyte source connector |
| `agents/connector-validator.md` | API research and requirements gathering |
| `agents/connector-generator.md` | Connector code generation |
| `agents/connector-fixer.md` | Error diagnosis and targeted repairs |
| `workflows/` | Shared validator, generator and fixer workflow content |
| `sdk-reference.md` | Connector SDK rules, patterns and examples |
| `tools/enter_configuration.py` | Optional local encryption of configuration values |
| `tools/run_connector.py` | Run a connector with runtime configuration |
| `tools/deploy_connector.py` | Deploy or redeploy a connector |

## Telemetry

This plugin collects anonymous usage data (skill name, plugin name and version, model, status, session ID, and timestamp) to help improve the product. No prompts, code, credentials, or personal information are collected. To opt out, add this to your shell profile:

```bash
export FIVETRAN_TELEMETRY_DISABLED=1
```
