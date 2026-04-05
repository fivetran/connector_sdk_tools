---
description: Fix errors in a Fivetran connector. Used internally by test-connector when code errors are detected.
user-invokable: false
---

> **Context**: This plugin is for the Fivetran Connector SDK (CSDK). "CSDK" is shorthand for "Connector SDK".

# Fix Fivetran Connector

Fix the connector issue described by the user: `$ARGUMENTS`

## Step 1: Problem Analysis

1. Read `connector.py` and `configuration.json` to understand the current implementation
2. Analyze the error message or user description
3. Identify the error location (specific line numbers and functions)

## Step 2: Error Classification

**CRITICAL**: Classify the error before attempting fixes.

### INFRA errors (infrastructure/network — do NOT change code):
- Network connectivity issues (connection refused, timeout, DNS errors)
- JVM/Java runtime errors
- SDK internal errors (gRPC, port 50051)
- SSL/certificate errors

**For INFRA errors**: Explain the infrastructure issue. If this is a first run, also mention it could be a credentials/config issue.

### FIRST_RUN errors (connector never succeeded — do NOT change code):
- Invalid API credentials or expired tokens
- Wrong API endpoints or URLs in config
- Missing permissions on the external service
- Invalid configuration values (non-string values, missing fields)

**For FIRST_RUN errors**: Explain that since the connector has never run successfully, it's likely a configuration issue. Ask the user to verify their credentials and configuration values. Do NOT modify code.

### CODE errors (implementation — fix the code):
- Syntax errors or import failures
- Logic bugs or incorrect SDK API usage
- Type annotation issues (`Dict[str, Any]`, `Generator`, `op.Operation`)
- Wrong logging methods (`log.error()` instead of `log.severe()`)
- Missing error handling or schema issues
- Incorrect data transformations

**For CODE errors**: Only classify as CODE if the connector has successfully run before. Proceed to fix the implementation.

## Step 3: Pattern Research (for CODE errors)

Use WebFetch to study correct patterns from the SDK examples:

1. Always check the basic structure:
   `https://raw.githubusercontent.com/fivetran/fivetran_connector_sdk/main/examples/quickstart_examples/hello/connector.py`

2. Match the error to the relevant example:
   - Authentication errors → fetch auth examples
   - Type/import errors → fetch hello example for correct patterns
   - Configuration errors → fetch configuration example
   - Data handling errors → fetch cursor/pagination examples

3. Compare current code with working examples to identify differences

## Step 4: Apply Fixes (for CODE errors)

1. Use Edit tool to apply targeted, minimal fixes
2. Document each change: what was changed and why
3. Follow SDK example patterns precisely

## Step 5: Validate

1. Use Read tool to verify changes were applied correctly
2. Check that the fix addresses the original error
3. Verify no new issues were introduced (imports, syntax, type hints)

## Step 6: Summary

Provide a clear summary:

```
ERROR_TYPE: INFRA|FIRST_RUN|CODE

PROBLEM IDENTIFIED:
<What caused the error>

SOLUTION APPLIED:
<For INFRA: Explain the infrastructure/network issue>
<For FIRST_RUN: What to check/configure>
<For CODE: What code changes were made and why>

FILES MODIFIED:
<List of files changed>
```

## Common Error Patterns

### Type Annotation Errors
- **Problem**: `Generator[op.Operation, None, None]`, `Dict[str, Any]`
- **Fix**: Replace with simple `dict`, `list` built-in types

### Logging Method Errors
- **Problem**: `AttributeError: 'Logging' object has no attribute 'error'`
- **Fix**: Replace `log.error()` with `log.severe()`

### Configuration Errors
- **Problem**: Non-string values in configuration.json
- **Fix**: Convert all values to strings

### Import/Syntax Errors
- **Problem**: Missing imports, incorrect SDK usage
- **Fix**: Use `from fivetran_connector_sdk import Connector, Operations as op, Logging as log`

### Connector Object Errors
- **Problem**: `connector` not found or defined inside `if __name__`
- **Fix**: Declare `connector = Connector(update=update, schema=schema)` in global scope
