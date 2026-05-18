---
name: deploy-connector
description: Package and deploy a Fivetran connector to Fivetran. Use when the user wants to deploy or ship their connector.
---

<!--
  GENERATED FILE — DO NOT EDIT.
  Canonical source: canonical/skills/deploy-connector/SKILL.md
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
   - No forbidden patterns (`Dict[str, Any]`, `Generator[op.Operation, ...]`, `op.Operation` in type hints)
3. **Configuration**: `configuration.json` starts with `ENCRYPTED:`. If it is plaintext JSON, stop and tell the user to enter credentials through `tools/enter_configuration.py` in a separate terminal. Do not read, print, copy, or deploy plaintext credential values.

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

If `deploy_connector.py` exits with "configuration.json is not encrypted", do not continue deployment. Direct the user to run:

macOS/Linux:
```bash
cd "<connector_directory>"
python "<plugin>/tools/enter_configuration.py" "configuration.json"
```

Windows PowerShell:
```powershell
cd "<connector_directory>"
python "<plugin>/tools/enter_configuration.py" "configuration.json"
```

Then re-run deploy after the user confirms the file is encrypted.

If the local encryption secret file does not exist yet, `enter_configuration.py` creates it before encrypting `configuration.json`.

### Prerequisite: `FIVETRAN_API_KEY`

If the user hasn't set the env var, the tool exits with a clear message. Direct the user to:

1. Create a Fivetran API key at https://fivetran.com/dashboard/user/api-config with `CONNECTOR:READ` permission (and `DESTINATION:READ` so destination lookup works).
2. Add it to their shell config.

   macOS/Linux:
   ```bash
   export FIVETRAN_API_KEY=...
   ```

   Windows PowerShell:
   ```powershell
   setx FIVETRAN_API_KEY "..."
   ```
3. Reload their shell and re-run the deploy command.

### If no destinations exist

If the user has zero destinations, the tool exits with a link to the destinations page. Direct the user to create one in the dashboard (requires warehouse credentials) and re-run deploy.

Reference: https://fivetran.com/docs/connector-sdk/working-with-connector-sdk#deploytheconnector

## Alternative: Manual Packaging

If the user prefers manual deployment (e.g., wants to inspect the package before upload):

1. Build the deployable archive:
   ```bash
   fivetran package
   ```
   This produces a ZIP containing `connector.py`, `configuration.json`, `requirements.txt` (or `pyproject.toml`), `README.md`, and any additional source files, respecting `.gitignore`.
2. Upload via the Fivetran dashboard.
