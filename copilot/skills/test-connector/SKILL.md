---
name: test-connector
description: Test a Fivetran connector by running fivetran debug and checking the results. Use when the user wants to validate or run their connector locally.
argument-hint: "Connector directory name (e.g., 'github_connector')"
---

<!--
  GENERATED FILE — DO NOT EDIT.
  Canonical source: canonical/skills/test-connector/SKILL.md
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
- `configuration.json` — connector settings as a flat JSON object with string values only
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

## Step 3: Configuration

Follow **Configuration entry** in `sdk-reference.md` only for missing values.
Reuse existing configuration and accept supplied ordinary values without requiring
interactive re-entry or encryption. Do not dump configuration into model context.
Collect missing secrets through the form or the user's local editor/terminal;
do not ask users to paste them into chat.

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

Once configuration is ready, run the connector once; reuse an already successful test:

```bash
python "<plugin>/tools/run_connector.py" "<connector_directory>" --timeout-seconds 600
```

The runner defaults to 120 seconds and accepts up to 600. Use 600 for debug
runs because the first run downloads and starts the Java tester. Set the
harness command timeout to 600 seconds as well.


This passes plaintext configuration through to `fivetran debug`; only existing encrypted fields require decryption. Plaintext configuration never requires an encryption key.

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

## Diagnosing a slow or stuck sync

If a local run takes a long time with no visible progress, don't assume it's hung — profile it
rather than guessing. Install py-spy into the connector's existing `.venv` (not supported on
Python 3.14 — use a lower version if that's what the `.venv` was created with), and profile
through `run_connector.py` rather than calling `fivetran debug` directly — `run_connector.py`
decrypts any `ENCRYPTED:v1:...` values in `configuration.json` before passing them through;
calling `fivetran debug` directly would pass that ciphertext as-is and can fail. Pass
`--subprocesses` so py-spy also samples the `fivetran` process `run_connector.py` launches, where
the connector code actually runs:

Use the connector's own `.venv` interpreter to launch `run_connector.py`, not whatever `python`
resolves to on `PATH` — that venv is the one guaranteed to be on the selected py-spy-compatible
version and to have `cryptography` installed for decrypting `ENCRYPTED:v1:...` values.

macOS/Linux:
```bash
cd "<connector_directory>"
uv pip install --python .venv/bin/python py-spy
.venv/bin/py-spy record -o cpu_profile.svg --subprocesses -- .venv/bin/python "<plugin>/tools/run_connector.py" "<connector_directory>" --timeout-seconds 600
```

Windows PowerShell:
```powershell
cd "<connector_directory>"
uv pip install --python .\.venv\Scripts\python.exe py-spy
.\.venv\Scripts\py-spy.exe record -o cpu_profile.svg --subprocesses -- .\.venv\Scripts\python.exe "<plugin>/tools/run_connector.py" "<connector_directory>" --timeout-seconds 600
```

Leave existing state alone by default, so the profile matches the actual slow run being
diagnosed. Only reset first (`.venv/bin/fivetran reset --force`, or the Windows equivalent) if
you specifically want to profile a full initial sync instead of the current incremental
workload — resetting replaces the workload being profiled, not just the state. This produces a flamegraph
SVG of CPU time; read it directly rather than asking the user to open it in a viewer — it's a
plain-text XML file. Each stack frame is a `<title>` element formatted roughly as
`function_name (file.py:line) (N samples, X.XX%)`; read the file and look at the widest boxes
(highest percentages) under `run_update` — that's the connector's own code. Ignore frames outside
`run_update`, they're SDK/tester framework overhead, not something to optimize.

Full reference, including how to read the flamegraph, common bottleneck patterns (sequential API
calls, row-by-row processing, repeated JSON parsing), and how production profiling differs from
local: https://fivetran.com/docs/connector-sdk/testing/connector-performance-analysis

## Diagnosing high memory usage

`fivetran debug` reports peak memory at the end of the run (e.g. `peak memory used by the debug
process: 0.06 GB`) and enforces a memory limit locally. If a run is close to or exceeds that
limit, follow **Memory Management** in `sdk-reference.md` for common causes, the fetch-chunk-
upsert-repeat fix, and how to pinpoint the allocating line with `tracemalloc`/`psutil`.
