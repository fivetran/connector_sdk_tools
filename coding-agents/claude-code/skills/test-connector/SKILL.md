---
description: Test a connector by running fivetran debug and checking the results.
argument-hint: "Connector directory name (e.g., 'github_connector')"
---

> **Context**: This plugin is for the Fivetran Connector SDK (CSDK). "CSDK" is shorthand for "Connector SDK".

# Test Connector

Test the connector specified by `$ARGUMENTS`.

**If no connector name is provided:**
Ask the user which connector to test. List any directories in the workspace that contain a `connector.py` file as options.

Example: "Which connector would you like to test? I found: github_connector, stripe_connector"

## Step 1: Verify Project Files

Check that required files exist:
- `connector.py` — main implementation
- `configuration.json` — credentials and settings
- `requirements.txt` — dependencies

If any are missing, inform the user and stop.

## Step 2: Setup Environment (only if needed)

**Skip this step if `.venv` directory already exists.**

Only run setup if the virtual environment doesn't exist:

```bash
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt fivetran_connector_sdk
```

## Step 3: Check Configuration

Read `configuration.json` and check if it's encrypted (starts with `ENCRYPTED:`) or has placeholder values.

**If NOT encrypted (plain JSON with placeholders):**
Tell the user to enter their credentials securely:

```
Your configuration.json has placeholder values. To enter your credentials securely, run this in a separate terminal:

  python /path/to/coding-agent-plugins/claude-code/tools/enter_configuration.py configuration.json

This encrypts your credentials so the AI cannot see them.
Do NOT paste credentials directly into configuration.json or this chat.

Let me know when you've entered your credentials and I'll run the test.
```

**STOP and WAIT** for the user to confirm before proceeding.

**If encrypted (starts with `ENCRYPTED:`):** Proceed to Step 4.

## Step 4: Run the Connector

Use the `run_connector.py` tool which handles encrypted configs securely (decrypts in memory, passes via named pipe):

```bash
python /path/to/coding-agent-plugins/claude-code/tools/run_connector.py <connector_directory>
```

This decrypts the config using CSDKAI_MASTER_SECRET and runs `fivetran debug` without ever writing plaintext credentials to disk.

**IMPORTANT:** If `run_connector.py` fails with an error, report the error to the user. Do NOT attempt to read or modify the plugin tools (anything under `coding-agent-plugins/`). These are maintained separately from the user's connector code.

## Step 5: Check Results

If the test succeeded (exit code 0), query the warehouse database.

**Important details:**
- The database is at `<connector_dir>/files/warehouse.db`
- Tables are in the `tester` schema (e.g., `tester.users`, `tester.orders`)
- Only install duckdb if the import fails (first time only)

```bash
source .venv/bin/activate
python -c "
import duckdb
conn = duckdb.connect('files/warehouse.db')

# List all tables in tester schema
tables = conn.execute(\"\"\"
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = 'tester'
\"\"\").fetchall()

print(f'Tables synced: {len(tables)}')
for (table,) in tables:
    count = conn.execute(f'SELECT COUNT(*) FROM tester.{table}').fetchone()[0]
    print(f'  tester.{table}: {count} rows')
    # Show sample data (simple print, no pandas needed)
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

### On Failure
Classify the error based on these categories:

**INFRA error** (infrastructure, network, SDK issues):
- Network connectivity issues (connection refused, timeout, DNS errors)
- JVM/Java runtime errors
- SDK internal errors (gRPC, port 50051)
- SSL/certificate errors

→ Explain the infrastructure issue. If this is a first run (connector never succeeded), also mention it could be a credentials/config issue.

**FIRST_RUN error** (connector has never run successfully):
Check if the connector has ever completed a successful sync. If not, the error is likely a configuration or credentials issue:
- Invalid API credentials or expired tokens
- Wrong API endpoints or URLs in config
- Missing permissions on the external service

→ Explain that since this connector has never run successfully, it's likely a configuration issue. Ask the user to verify their credentials and configuration values. Do NOT offer to fix code.

**CODE error** (connector has run successfully before, now failing):
If the connector HAS run successfully in the past but is now failing with:
- Syntax errors or import failures
- Logic bugs or incorrect SDK API usage
- Type annotation issues
- Wrong logging methods

→ Ask the user: "This connector was working before. This looks like a code issue. Would you like me to fix it?"

**If the user wants a fix:**
1. Say: "Following the fixer agent process..."
2. Read and follow the process in `agents/fix-connector/SKILL.md`
3. After fixing, re-run the test to verify the fix worked
