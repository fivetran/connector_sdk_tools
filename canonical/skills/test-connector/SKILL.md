---
name: test-connector
description: Test a Fivetran connector by running fivetran debug and checking the results. Use when the user wants to validate or run their connector locally.
argument-hint: "Connector directory name (e.g., 'github_connector')"
---

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
- `configuration.json` — connector settings with encrypted field values
- `requirements.txt` — dependencies

If any are missing, inform the user and stop.

## Step 2: Setup Environment (only if needed)

**Skip if `.venv` already exists.**

macOS/Linux:
```bash
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt fivetran_connector_sdk
```

Windows PowerShell:
```powershell
uv venv .venv
uv pip install --python .\.venv\Scripts\python.exe -r requirements.txt fivetran_connector_sdk
```

## Step 3: Credential Gate

Do not manually inspect values in `configuration.json`. The secure runner is the configuration loader.

**HARD RULES — violating any of these is a failure:**
- DO NOT use `AskUserQuestion` (or any checkbox / choice-menu / multi-option UI) to ask how the user wants to enter credentials. There is exactly one way.
- DO NOT present "Tell me the values to use" or any chat-based credential-entry choice.
- DO NOT ask the user to paste configuration values in chat.
- DO NOT ask the user to show you fields from `configuration.json`.
- DO NOT run `enter_configuration.py` yourself. The user must run it in their own separate terminal.
- DO NOT print, quote, summarize, or expose values from `configuration.json`.
- DO NOT ask any credential-related question before running the secure runner.

Run the secure runner immediately:

```bash
python <plugin>/tools/run_connector.py <connector_directory>
```

If the runner exits because an encrypted value cannot be decrypted, relay this exact secure flow as plain text (substitute `<plugin>`, `<connector_directory>` with actual paths), then stop and wait. Use one fenced command block: `bash` on macOS/Linux, `powershell` on Windows. Quote both paths. Do not insert a line break inside the `python` command.

````text
I can't run the connector until the encrypted configuration values can be decrypted. To refresh configuration values securely, open a separate terminal, then run:

```bash
cd "<connector_directory>"
python "<plugin>/tools/enter_configuration.py" "configuration.json"
```

The script will prompt for the configuration fields and encrypt values in place. I never see plaintext configuration values. Let me know when it's done and I'll run the test.
If the local encryption secret file does not exist yet, the script creates it first.
````

Do not use a choice UI for chat-based credential entry.

## Step 4: Run the Connector

**If the connector's schema or primary keys changed since the last local test**, reset the local
state first so the run simulates a clean initial sync (clears `warehouse.db` and `state.json`; it
does not touch credentials):

macOS/Linux:
```bash
cd "<connector_directory>" && .venv/bin/fivetran reset --force
```

Windows PowerShell:
```powershell
cd "<connector_directory>"; .\.venv\Scripts\fivetran.exe reset --force
```

If Step 3 already ran the secure runner and it succeeded, do not run it again. If the user returned after encrypting configuration values, run the secure runner:

```bash
python <plugin>/tools/run_connector.py <connector_directory>
```

This decrypts configuration values using the local encryption secret file and runs `fivetran debug` without writing plaintext values to disk.

**IMPORTANT**: If `run_connector.py` fails, report the error to the user. Do NOT read or modify plugin tools.

## Step 5: Check Results

If the test succeeded (exit code 0), query the DuckDB warehouse:

macOS/Linux:
```bash
.venv/bin/python -c "
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

Windows PowerShell:
```powershell
.\.venv\Scripts\python.exe -c 'import duckdb; conn = duckdb.connect("files/warehouse.db"); tables = conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = ''tester''").fetchall(); print("Tables synced:", len(tables)); [print("  tester." + table + ": " + str(conn.execute("SELECT COUNT(*) FROM tester." + table).fetchone()[0]) + " rows") for (table,) in tables]; conn.close()'
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
