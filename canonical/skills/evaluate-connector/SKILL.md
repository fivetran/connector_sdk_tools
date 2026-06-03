---
name: evaluate-connector
description: Evaluate a Fivetran connector for correctness, SDK compliance, security, and reliability. Use when the user wants a code review or quality report before deploying.
argument-hint: "Connector directory name (e.g., 'github_connector')"
---

> **Context**: This plugin is for the Fivetran Connector SDK (CSDK). "CSDK" is shorthand for "Connector SDK".

# Evaluate Connector

**FIRST**: Read `sdk-reference.md` from the plugin directory to load SDK rules and patterns.

Perform a static code evaluation of the connector. This is a read-only analysis — do NOT modify any files.

**If no connector name is provided:**
Ask which connector to evaluate. List any directories in the workspace that contain a `connector.py` file as options.

## Step 1: Read Connector Code

Read all source files in the connector directory:
- `connector.py` — required; main implementation
- Any other `.py` files present
- `requirements.txt` — if present, check for incorrectly declared pre-installed packages

Do NOT read or log any values from `configuration.json`.

If `connector.py` is missing, tell the user and stop.

## Step 2: Evaluate

Analyze the code against the criteria below. Be deterministic and conservative — only flag issues with concrete code evidence. Do NOT flag theoretical or hypothetical problems.

---

> **CRITICAL SDK RULE — read before evaluating anything:**
> SDK operations (`op.upsert`, `op.update`, `op.delete`, `op.checkpoint`) must be called **directly**. They are NOT generators and must NEVER be used with `yield` or `yield from`.
> - WRONG: `yield op.upsert(table="x", data=d)`
> - CORRECT: `op.upsert(table="x", data=d)`
>
> `update()` is a plain function, not a generator. `yield from` is only valid inside helper pagination functions that stream raw API records — it is never valid with SDK operations.
>
> If you find code that calls SDK operations without `yield`, that is **correct**. Do not flag it.

---

### REQUIRED Issues — Must Fix

Flag as `required` only when the code clearly demonstrates the problem.

**1. Memory & Resource Management**
- Entire dataset loaded into memory before processing (e.g., accumulating all records in a list before iterating)
- Files or connections opened without a context manager and without explicit `.close()`
- Unbounded data structures that grow without limits

**2. SDK Compliance**
- `update(configuration, state)` function must exist and be passed to `Connector()` instantiation
- At least one of `op.upsert()`, `op.update()`, `op.delete()`, or `op.truncate()` must be called
- `op.checkpoint()` must be called
- SDK operations (`op.upsert`, `op.update`, `op.delete`, `op.truncate`, `op.checkpoint`) must be called directly — never with `yield` or `yield from`:
  - WRONG: `yield op.upsert(table="x", data=d)`
  - CORRECT: `op.upsert(table="x", data=d)`
- `update()` must not return anything — SDK operations return `None`
- Schema: only `table`, `primary_key`, `columns` keys are valid — any other key is an error
- Schema data types: if `columns` are specified, only `BOOLEAN`, `SHORT`, `INT`, `LONG`, `FLOAT`, `DOUBLE`, `DECIMAL`, `STRING`, `BINARY`, `JSON`, `XML`, `NAIVE_DATE`, `NAIVE_DATETIME`, `UTC_DATETIME` are valid — any other type name is an error
- Declaring `columns` with valid types is **correct and supported** — do NOT flag it as an issue. Declaring a `primary_key` for each table is recommended.
- Logging: preferred methods are `log.debug()`, `log.info()`, `log.warning()`, `log.error()`, `log.critical()` — flag `print()`, `logging.*`, `logger.*` as required issues
- Type hints: `Generator[op.Operation, None, None]` or any use of `op.Operation` in type hints is invalid — use plain `dict` and `list` only; never import from `typing` for SDK function signatures
- `exit()` must never be used — use `raise RuntimeError(...)` instead
- `connector = Connector(...)` must be at module (global) scope, not inside `if __name__ == "__main__"` or any function

**3. Security**
- Credentials, tokens, or secrets stored in the `state` dict (state is persisted to disk unencrypted)
- Secrets or PII exposed in log messages (e.g., `log.info(f"record: {data}")`)
- Hardcoded credentials in source code

**4. Data Reliability**
- HTTP responses not validated — missing `raise_for_status()` or equivalent status code check
- Infinite loops without a termination condition
- Missing pagination or streaming for API calls that return large datasets
- Cursor/state updated **before** processing the record (should be after):
  - WRONG: `cursor = data['updated_at']` then `op.upsert(...)`
  - CORRECT: `op.upsert(...)` then `cursor = data['updated_at']`

**5. Exception Handling**
- Missing error handling around network, file, or database operations
- Exceptions caught but silently ignored (`except Exception: pass`)

---

### GOOD_TO_HAVE Issues — Suggestions

**1. Performance**
- HTTP requests missing a `timeout` parameter
- Missing retry logic for transient network failures

**2. Code Quality**
- Functions over 50 lines without clear decomposition
- Missing input validation for required configuration keys
- Dead or duplicate code
- `requirements.txt` lists `requests` or `fivetran_connector_sdk` — these are pre-installed in the runtime and must not be declared
- Schema declares a type for **every** column — declaring all columns forfeits the SDK's type inference and schema evolution. Prefer declaring types only where a specific type must be forced. (Declaring types for *some* columns is fine — do not flag that.)
- No `primary_key` declared for a table — Fivetran will create a surrogate `_fivetran_id` key; declaring an explicit primary key is recommended
- `log.fine()` or `log.severe()` used — these are deprecated Java-style aliases; prefer `log.debug()` and `log.error()` respectively

**3. Reliability**
- Retries without exponential backoff
- String timestamp comparison without datetime parsing (can fail across timezones)
- Pagination logic that could silently skip records

---

### Do NOT Flag
- Code style or formatting preferences
- Theoretical edge cases not reachable in the actual execution path
- Issues already handled elsewhere in the code
- Cursor checkpoint placed after the loop when an empty page breaks before the cursor update — this is correct behavior
- `columns` declared with valid data types — declaring types is explicitly supported by the SDK and useful for forcing a specific type. Only flag declaring a type for *every* column (good_to_have).
- Reading credentials from the `configuration` dict — Fivetran encrypts configuration
- Any JSON-serializable value stored in state — all are valid
- Datetime string vs datetime object in `op.upsert()` data — SDK accepts both
- `yield from` inside a helper pagination generator that streams raw API records — this is correct and unrelated to SDK operations
- `log.fine()` or `log.severe()` as a required issue — they are deprecated but still work; flag as good_to_have only
- A top-level `encrypted` field in `configuration.json` — this is normal; the plugin encrypts credentials there at runtime

---

## Step 3: Score

Start at 100 and deduct based on issues found:

**Required deductions:**
- Critical (security breach, data loss, SDK violation): −25 to −30 per issue
- Major (silent failures, memory exhaustion): −15 to −20 per issue
- Medium (reliability risk): −10 to −15 per issue

**Good-to-have deductions:**
- Significant omission: −3 to −5 per issue
- Minor suggestion: −1 to −2 per issue

Compute three subscores:
- `required_score`: 100 minus required deductions
- `good_to_have_score`: 100 minus good-to-have deductions
- `sdk_adherence_score`: 100 minus SDK-specific violations only

Floor all scores at 0.

---

## Step 4: Report

Present findings using this structure. Omit any section that has no issues.

```
## Evaluation Report — <connector_name>

### Score
Overall: <score>/100
- SDK Adherence: <sdk_adherence_score>/100
- Required: <required_score>/100
- Good to Have: <good_to_have_score>/100

### Required Issues
**[<tag>] <issue title>**
- Problem: <what is wrong>
- Location: <function name or line reference>
- Current code:
  ```python
  <offending snippet>
  ```
- Fix:
  ```python
  <corrected snippet>
  ```

### Good to Have
<same structure as above>

### Summary
<2–3 sentence overall assessment>
```

**Tags:** `memory management` | `security` | `resource management` | `reliability` | `exception handling` | `input validation` | `configurability` | `code quality` | `sdk compliance` | `others`

If no issues are found in a category, write `None found.`

Do NOT suggest fixes for `good_to_have` issues unless the fix is a straightforward one-liner. Do NOT modify any files.
