---
name: test-connector
description: Test a Fivetran connector by running fivetran debug and checking the results. Use when the user wants to validate or run their connector locally.
argument-hint: "Connector directory name (e.g., 'github_connector')"
---

<!--
  GENERATED FILE — DO NOT EDIT.
  Canonical source: coding-agents/skills/test-connector/SKILL.md
  Regenerate with: bash scripts/sync-plugins.sh
-->

> **Context**: This plugin is for the Fivetran Connector SDK (CSDK). "CSDK" is shorthand for "Connector SDK".

# Test Connector

**FIRST**: Read `sdk-reference.md` from the plugin directory to load SDK rules and patterns.

Test the connector specified by the user.

**If no connector name is provided:**
Ask which connector to test. List any directories in the workspace that contain a `connector.py` file as options.

Example: "Which connector would you like to test? I found: github_connector, stripe_connector"

## Step 1: Verify Project Files

Check that required files exist in the connector directory:
- `connector.py` — main implementation
- `configuration.json` — credentials and settings
- `requirements.txt` — dependencies

If any are missing, inform the user and stop.

## Step 2: Setup Environment (only if needed)

**Skip if `.venv` already exists.**

```bash
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt fivetran_connector_sdk
```

## Step 3: Check Configuration

Read `configuration.json`. Check if encrypted (starts with `ENCRYPTED:`) or has placeholder values.

**If NOT encrypted (plain JSON with placeholders):**
Tell the user to enter credentials securely in a separate terminal:

```
python <plugin>/tools/enter_configuration.py configuration.json
```

This encrypts credentials so the AI cannot see them. Do NOT paste credentials directly into `configuration.json` or this chat.

**STOP and WAIT** for the user to confirm before proceeding.

**If encrypted:** proceed to Step 4.

## Step 4: Run the Connector

Use the secure runner:

```bash
python <plugin>/tools/run_connector.py <connector_directory>
```

This decrypts the config using `FIVETRAN_CSDK_MASTER_SECRET` and runs `fivetran debug` without ever writing plaintext credentials to disk.

**IMPORTANT**: If `run_connector.py` fails, report the error to the user. Do NOT read or modify plugin tools.

## Step 5: Check Results

If the test succeeded (exit code 0), query the DuckDB warehouse:

```bash
source .venv/bin/activate
python -c "
import duckdb
conn = duckdb.connect('files/warehouse.db')
tables = conn.execute(\"\"\"
    SELECT table_name FROM information_schema.tables WHERE table_schema = 'tester'
\"\"\").fetchall()
print(f'Tables synced: {len(tables)}')
for (table,) in tables:
    count = conn.execute(f'SELECT COUNT(*) FROM tester.{table}').fetchone()[0]
    print(f'  tester.{table}: {count} rows')
    rows = conn.execute(f'SELECT * FROM tester.{table} LIMIT 3').fetchall()
    cols = [desc[0] for desc in conn.description]
    print(f'    Columns: {cols}')
    for row in rows:
        print(f'    {row}')
    print()
conn.close()
"
```

## Step 6: Report Results

### On Success
Report which tables were synced and how many rows each.

### On Failure — Classify the Error

**INFRA error** (infrastructure/network — do NOT change code):
- Connection refused, timeout, DNS errors
- JVM/Java runtime errors
- SDK internal errors (gRPC, port 50051)
- SSL/certificate errors

→ Explain the infrastructure issue.

**FIRST_RUN error** (connector has never run successfully — do NOT change code):
- Invalid API credentials or expired tokens
- Wrong API endpoints or URLs in config
- Missing permissions on the external service

→ Explain that since the connector has never run successfully, it's likely a configuration issue. Ask the user to verify credentials and config values.

**CODE error** (connector has run successfully before, now failing, OR the error is clearly a code bug):
- Syntax errors or import failures
- Logic bugs or incorrect SDK API usage
- Type annotation issues
- Wrong logging methods

→ Ask: "This looks like a code issue. Would you like me to fix it?"

**If the user wants a fix:** apply the fixer workflow (see `workflows/fixer.md` in the plugin, or — in plugins that support subagents — invoke the `connector-fixer` subagent). After fixing, re-run the test to verify.
