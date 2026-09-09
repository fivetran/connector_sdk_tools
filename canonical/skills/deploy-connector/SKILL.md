---
name: deploy-connector
description: Package and deploy a Fivetran connector to Fivetran. Use when the user wants to deploy or ship their connector.
---

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
3. **Configuration**: `configuration.json` is JSON. Plaintext string values are supported; do not require custom encryption. Do not read, print, copy, or deploy plaintext configuration values in chat.

## Step 2: Run Final Test

Use the secure runner:

```bash
python <plugin>/tools/run_connector.py <connector_directory> --timeout-seconds 600
```

The runner defaults to 120 seconds and accepts up to 600. Use 600 for debug
runs because the first run downloads and starts the Java tester. Set the
harness command timeout to 600 seconds as well.


If the test fails, classify the error (INFRA / FIRST_RUN / CODE) and — for CODE errors — apply the fixer workflow (see `workflows/fixer.md` in the plugin, or — in plugins that support subagents — invoke the `connector-fixer` subagent).

## Step 3: Deploy

For an existing connection, use its ID so the tool reuses its current name and
destination without listing destinations or prompting:

```bash
python <plugin>/tools/deploy_connector.py <connector_directory> --connection-id <id>
```

For a new connection, supply the destination (group) name and optionally a
connection name; otherwise the connection name is derived from the directory:

```bash
python <plugin>/tools/deploy_connector.py <connector_directory> --destination <name> --connection <name>
```

The tool reads `FIVETRAN_API_KEY`, passes runtime configuration through a named
pipe, and invokes `fivetran deploy --destination <name> --connection <name> --force`.
For an existing connection it reads connection details and then that connection's
group details. Do not combine `--connection-id` with name or destination overrides.

If no destination is supplied for a new connection, a single available destination
is selected automatically. Multiple destinations require an interactive terminal
or an explicit argument. Closed input ends the command; do not retry without
providing the target.

For missing configuration or unusable encrypted values, follow **Configuration
entry** in `sdk-reference.md`. Plaintext values are supported without a key; do
not require re-entry or encryption of user-supplied values.

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

To update a deployed connection, use `--connection-id <id>`. This preserves its
name and destination even when the recovered project directory has a different
name. Redeployment replaces code and supplied configuration; it does not itself
unpause the connection. Verify connection health after deployment and use the
explicit start-sync path only when authorized.

## Alternative: Manual Packaging

If the user prefers manual deployment (e.g., wants to inspect the package before upload):

1. Build the deployable archive:
   ```bash
   fivetran package
   ```
   This produces a ZIP containing `connector.py`, `configuration.json`, `requirements.txt` (or `pyproject.toml`), `README.md`, and any additional source files, respecting `.gitignore`.
2. Upload via the Fivetran dashboard.
