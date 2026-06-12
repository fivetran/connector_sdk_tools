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
3. **Configuration**: `configuration.json` is JSON. `enter_configuration.py` encrypts every field by default using inline `ENCRYPTED:v1:<key_id>:local-fernet:` values, but user-chosen plaintext values are also accepted. Do not read, print, copy, or deploy plaintext configuration values in chat.

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
2. Calls `GET /v1/groups` to discover the destination (group) name, picking the single one automatically or prompting if more than one exists.
3. Derives the connection name from the connector directory name (sanitized to Fivetran rules). To set it explicitly, pass `--connection <name>` (must begin with `_` or a lowercase letter; only `_`, lowercase, digits).
4. Invokes `fivetran deploy --destination <name> --connection <name> --force` with the runtime configuration passed via named pipe after decrypting configuration values in memory. `--force` auto-answers the overwrite prompts so redeploys don't hang.
5. Captures and prints the Connection ID from the deploy log.

If deploy fails because an encrypted value cannot be decrypted, direct the user to run:

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

Then re-run deploy after the user confirms configuration values have been refreshed.

If the local encryption secret file does not exist yet, `enter_configuration.py` creates it before encrypting configuration values.

### Prerequisite: `FIVETRAN_API_KEY`

If the user hasn't set the env var, the tool exits with a clear message. Direct the user to:

1. Create a Fivetran API key at https://fivetran.com/dashboard/user/api-config. It must be the base64-encoded `{key}:{secret}` string, with permission to manage connections and read destinations (so destination lookup, deploy, and unpause all work).
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

## Step 4: Offer to Start the Initial Sync

A newly deployed connection is created **paused**. Deploying does not start a sync.

After a successful deploy, surface the Connection ID and dashboard link the tool printed, then **ask the user** whether to start the initial sync now. State plainly that starting the sync begins consuming [MAR](https://fivetran.com/docs/core-concepts/usage-based-pricing#monthlyactiverows). Do not start it automatically.

Only if the user explicitly confirms, unpause the connection:

```bash
python <plugin>/tools/deploy_connector.py <connector_directory> --start-sync --connection-id <id>
```

This calls `PATCH /v1/connections/{id}` with `{"paused": false}`; Fivetran then begins the initial sync. If the user declines, tell them they can start it anytime from the dashboard link or by re-running the command above.

## Redeploying (updating an existing connection)

To update a deployed connection, redeploy with the **same connection name and destination** (the tool derives the same name from the directory, or pass `--connection <name>`). The tool's `--force` flag auto-answers the "update connection code / overwrite configuration.json" prompts. Redeploying replaces the connection's code; the wrapper decrypts local encrypted values in memory and passes runtime configuration to `fivetran deploy`, replacing the connection's stored configuration values. A redeploy does not pause an already-running connection — the in-progress sync finishes on the old code, and the next sync uses the new code.

## Alternative: Manual Packaging

If the user prefers manual deployment (e.g., wants to inspect the package before upload):

1. Build the deployable archive:
   ```bash
   fivetran package
   ```
   This produces a ZIP containing `connector.py`, `configuration.json`, `requirements.txt` (or `pyproject.toml`), `README.md`, and any additional source files, respecting `.gitignore`.
2. Upload via the Fivetran dashboard.
