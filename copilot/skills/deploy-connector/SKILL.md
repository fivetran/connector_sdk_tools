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


If the user wants to bind or rebind a connection to an existing package (see
**Reusable Packages (1:N)** below) via `--package-id`, no local code is uploaded — skip this
step and go straight to **Step 3**.

Otherwise, verify the connector is ready:

1. **Files exist**: `connector.py`, `requirements.txt`, `README.md`; `configuration.json` when supplying configuration.
2. **Code quality**: Read `connector.py` and check for:
   - Both `schema()` and `update()` functions present
   - `connector = Connector(update=update, schema=schema)` in global scope
   - `if __name__ == "__main__": connector.debug()` entry point
   - No forbidden patterns (`Dict[str, Any]`, `Generator[op.Operation, ...]`, `op.Operation` in type hints)
3. **Configuration**: `configuration.json` is JSON. Plaintext string values are supported; do not require custom encryption. Do not read, print, copy, or deploy plaintext configuration values in chat.

## Step 2: Run Final Test

Use the secure runner:

```bash
python "<plugin>/tools/run_connector.py" "<connector_directory>" --timeout-seconds 600
```

The runner defaults to 120 seconds and accepts up to 600. Use 600 for debug
runs because the first run downloads and starts the Java tester. Set the
harness command timeout to 600 seconds as well.


If the test fails, classify the error (INFRA / FIRST_RUN / CODE) and — for CODE errors — apply the fixer workflow (see `workflows/fixer.md` in the plugin, or — in plugins that support subagents — invoke the `connector-fixer` subagent).

## Step 3: Deploy

For an existing connection, use its ID so the tool reuses its current name and
destination without listing destinations or prompting:

```bash
python "<plugin>/tools/deploy_connector.py" "<connector_directory>" --connection-id "<id>"
```

For a new connection, confirm the connection name with the user before deploying — do not
silently derive it from the directory name and deploy. Tell the user what name will be used
(the directory name, if that's the default you're about to pass) and let them override it.
Supply the destination (group) name and the confirmed connection name:

```bash
python "<plugin>/tools/deploy_connector.py" "<connector_directory>" --destination "<name>" --connection "<name>"
```

If the harness has no way to ask (no input channel), state the name you're about to use and
give the user a chance to stop you before the deploy call runs.

The tool reads `FIVETRAN_API_KEY`, passes local configuration through a named
pipe when present, and invokes `fivetran deploy --destination <name> --connection <name> --force`.
For an existing connection it reads connection details and then that connection's
group details. Do not combine `--connection-id` with name or destination overrides.

If no destination is supplied for a new connection, a single available destination
is selected automatically. Multiple destinations require a selection on stdin or an explicit argument.
Harnesses without an input channel should pass the target explicitly. Closed
input ends the command; do not retry without providing the target.

A missing local configuration file is allowed; the SDK may still use environment
configuration. Preserve production settings during code repairs and verify the
installed SDK's configuration behavior before deploying. Do not confuse local
test inputs with the production configuration.

For required configuration or unusable encrypted values, follow **Configuration
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

## Step 4: Offer to Start the Initial Sync (new connections)

A newly deployed connection is created **paused**. Deploying does not start a sync.

After a successful deploy, surface the Connection ID and dashboard link the tool printed, then **ask the user** whether to start the initial sync now. State plainly that starting the sync begins consuming [MAR](https://fivetran.com/docs/core-concepts/usage-based-pricing#monthlyactiverows). Do not start it automatically.

Only if the user explicitly confirms, unpause the connection:

```bash
python "<plugin>/tools/deploy_connector.py" "<connector_directory>" --start-sync --connection-id "<id>"
```

This calls `PATCH /v1/connections/{id}` with `{"paused": false}`; Fivetran then begins the initial sync. If the user declines, tell them they can start it anytime from the dashboard link or by re-running the command above.

## Redeploying (updating an existing connection)

To update a deployed connection, use `--connection-id <id>`. This preserves its
name and destination even when the recovered project directory has a different
name. Redeployment replaces code and supplied configuration; it does not itself
unpause the connection.

If the connection's current code package is shared with other connections (see **Reusable
Packages (1:N)** below), a normal redeploy is refused. A plain redeploy always uploads a
brand-new package and points the connection at it (it never edits the old package's code in
place), which would silently detach this connection from the shared group — so the tool blocks
it instead. Rebind it explicitly with `--package-id <id>` to a *different* package if that's
genuinely what's wanted, or confirm with the user whether they actually want a one-off divergent
copy (in which case, deploy to a different connection rather than forcing this one off its shared
package).

## Reusable Packages (1:N)

A reusable package lets the *same* uploaded code run identically across many connections (e.g.
one per customer/tenant), instead of every connection holding its own independent copy. This is a
Private Preview CLI feature — the flags exist and work but are hidden from `fivetran --help`.

**Creating a package without a connection** (direct CLI call, not through the wrapper — these
subcommands have no configuration to protect, so the wrapper's encryption/pipe handling isn't
needed):

```bash
fivetran package create "<connector_directory>" --yes
```

This uploads the project and prints a server-assigned `package id: <id>`. Share that ID with the
user; it's what every bound connection will reference.

**Updating an existing package's code** (pushes new code to every connection using it, on their
next sync):

```bash
fivetran package update "<package-id>" "<connector_directory>" --yes
```

**Always pass `--yes`** on `package create`/`package update`: like `deploy`, both run the same
`requirements.txt` dependency check, which otherwise prompts interactively (and would block an
agent run) when it detects missing/mismatched dependencies. `--yes` auto-accepts and lets the tool
fix `requirements.txt` for you; prefer it over `--force`, which skips the dependency check
entirely instead of just auto-answering its prompt.

**Listing packages in the account** (package ID and how many connections use each):

```bash
fivetran package list
```

**Binding a new connection to an existing package** (no local code is uploaded — confirm the
connection name with the user first, same as a normal new-connection deploy in Step 3):

```bash
python "<plugin>/tools/deploy_connector.py" "<connector_directory>" --destination "<name>" --connection "<name>" --package-id "<package-id>"
```

**Rebinding an existing connection to a (possibly different) package**:

```bash
python "<plugin>/tools/deploy_connector.py" "<connector_directory>" --connection-id "<id>" --package-id "<package-id>"
```

- If the connection already uses that package, this is a no-op.
- Otherwise it replaces the connection's code (and configuration, if supplied) with the target
  package's. The wrapper always passes `--force`, so this happens without an interactive prompt —
  confirm the rebind with the user before running it, the same way you'd confirm any other
  destructive redeploy.
- If the connection's previous package was shared with other connections, the tool reports that
  the connection left that package group; the other connections are unaffected and keep using it.

`<connector_directory>` only needs to exist as a directory for this flow — `connector.py` is not
required locally since no code is uploaded.

## Alternative: Manual Packaging

If the user prefers manual deployment (e.g., wants to inspect the package before upload):

1. Build the deployable archive:
   ```bash
   fivetran package
   ```
   This produces a ZIP containing `connector.py`, `configuration.json`, `requirements.txt` (or `pyproject.toml`), `README.md`, and any additional source files, respecting `.gitignore`.
2. Upload via the Fivetran dashboard.
