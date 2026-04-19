---
name: fix-connector
description: Diagnose and fix errors in a Fivetran connector. Use when the user reports errors, test failures, or issues with an existing connector.
---

# Fix Fivetran Connector

**FIRST**: Read `sdk-reference.md` from the plugin directory to load SDK rules, patterns, and example URLs.

Fix the connector issue described by the user.

## Step 1: Problem Analysis

1. Read `connector.py` and `configuration.json` to understand the current implementation
2. Parse the error message or user description
3. Identify the error location (line numbers, functions involved)

## Step 2: Error Classification (REQUIRED)

Classify every error as one of:

### INFRA errors (infrastructure/network — do NOT change code)
- Network connectivity (connection refused, timeout, DNS)
- JVM/Java runtime errors
- SDK internal errors (gRPC, port 50051)
- SSL/certificate errors

**Action**: Explain the infrastructure issue. If this is a first run, also mention it could be a credentials/config issue.

### FIRST_RUN errors (connector never succeeded — do NOT change code)
- Invalid API credentials or expired tokens
- Wrong API endpoints or URLs in config
- Missing permissions on the external service
- Invalid config values (non-string values, missing fields)

**Action**: Explain that since the connector has never run successfully, it's likely a configuration issue. Ask the user to verify credentials and values. Do NOT modify code.

### CODE errors (implementation — fix the code)
- Syntax errors or import failures
- Logic bugs or incorrect SDK API usage
- Type annotation issues (`Dict[str, Any]`, `Generator`, `op.Operation`)
- Wrong logging methods (`log.error()` instead of `log.severe()`)
- Missing error handling or schema issues
- Incorrect data transformations

**Action**: Proceed to fix using Steps 3-5 below.

Only classify as CODE if the connector has successfully run before OR the error is clearly a code bug.

## Step 3: Pattern Research (for CODE errors)

Study correct patterns from the SDK examples (see URLs in `sdk-reference.md`):

1. Always check the hello world example for basic structure
2. Match the error to the relevant example:
   - Authentication errors → auth examples
   - Type/import errors → hello world for correct patterns
   - Configuration errors → configuration example
   - Data handling errors → cursor/pagination examples
3. Compare current code with working examples to find differences

## Step 4: Apply Fixes (for CODE errors)

1. Make targeted, minimal changes
2. Document each change: what and why
3. Follow SDK example patterns precisely

## Step 5: Validate

1. Read back modified files
2. Confirm the fix addresses the original error
3. Check no new issues introduced (imports, syntax, type hints)

## Step 6: Summary

```
ERROR_TYPE: INFRA|FIRST_RUN|CODE

PROBLEM IDENTIFIED:
<what caused the error>

SOLUTION APPLIED:
<For INFRA: infrastructure/network issue explanation>
<For FIRST_RUN: what to check/configure>
<For CODE: code changes made and why>

FILES MODIFIED:
<list>
```

## Common Error Patterns

| Pattern | Fix |
|---------|-----|
| `log.error()` | Replace with `log.severe()` |
| `Dict[str, Any]`, `Generator[...]` | Use simple `dict`, `list` |
| `connector` not in global scope | Move to module level |
| Data types in schema | Remove, keep only table names and primary keys |
| `yield op.upsert(...)` | Remove yield, call directly |
| Non-string config values | Convert all to strings |

**IMPORTANT:**
- Never modify plugin tools (anything under the plugin directory). Only fix user connector code.
- If configuration.json starts with `ENCRYPTED:`, this is normal — do NOT try to "fix" it.
