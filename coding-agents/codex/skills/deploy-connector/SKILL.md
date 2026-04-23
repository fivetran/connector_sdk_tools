---
name: deploy-connector
description: Package and deploy a Fivetran connector to Fivetran. Use when the user wants to deploy or ship their connector.
---

<!--
  GENERATED FILE — DO NOT EDIT.
  Canonical source: coding-agents/skills/deploy-connector/SKILL.md
  Regenerate with: bash scripts/sync-plugins.sh
-->

> **Context**: This plugin is for the Fivetran Connector SDK (CSDK). "CSDK" is shorthand for "Connector SDK".

# Deploy Fivetran Connector

**FIRST**: Read `sdk-reference.md` from the plugin directory to load SDK rules and patterns.

Package and deploy the connector in the current directory.

## Step 1: Pre-Deployment Validation

Verify the connector is ready:

1. **Files exist**: `connector.py`, `configuration.json`, `requirements.txt`, `README.md`
2. **Code quality**: Read `connector.py` and check for:
   - Both `schema()` and `update()` functions present
   - `connector = Connector(update=update, schema=schema)` in global scope
   - `if __name__ == "__main__": connector.debug()` entry point
   - No forbidden patterns (`log.error()`, `Dict[str, Any]`, `Generator`)
3. **Configuration**: `configuration.json` is valid JSON with string-only values.

## Step 2: Run Final Test

Use the secure runner:

```bash
python <plugin>/tools/run_connector.py <connector_directory>
```

If the test fails, classify the error (INFRA / FIRST_RUN / CODE) and — for CODE errors — apply the fixer workflow (see `workflows/fixer.md` in the plugin, or — in plugins that support subagents — invoke the `connector-fixer` subagent).

## Step 3: Deploy

The deploy tool auto-discovers the destination via the Fivetran REST API — you only need to run:

```bash
python <plugin>/tools/deploy_connector.py <connector_directory>
```

The tool:
1. Reads `FIVETRAN_API_KEY` from the environment.
2. Calls `GET /v1/groups` and `GET /v1/groups/{id}/destinations` to discover the user's groups and destinations.
3. Picks the single group/destination automatically, or prompts the user to choose if more than one exists.
4. Invokes `fivetran deploy` with the chosen destination and the encrypted configuration (passed via named pipe, never written to disk).

### Prerequisite: `FIVETRAN_API_KEY`

If the user hasn't set the env var, the tool exits with a clear message. Direct the user to:

1. Create a Fivetran API key at https://fivetran.com/dashboard/user/api-config with `CONNECTOR:READ` permission (and `DESTINATION:READ` so destination lookup works).
2. Add it to their shell config:
   ```bash
   export FIVETRAN_API_KEY=...
   ```
3. Reload their shell and re-run the deploy command.

### If no destinations exist

If the user has zero destinations, the tool exits with a link to the destinations page. Direct the user to create one in the dashboard (requires warehouse credentials) and re-run deploy.

Reference: https://fivetran.com/docs/connector-sdk/working-with-connector-sdk#deploytheconnector

## Alternative: Manual Packaging

If the user prefers manual deployment:

1. Create a ZIP file:
   ```bash
   zip -r connector-package.zip connector.py configuration.json requirements.txt README.md
   ```
2. Upload via the Fivetran dashboard.
