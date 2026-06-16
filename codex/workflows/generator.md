<!--
  GENERATED FILE — DO NOT EDIT.
  Canonical source: canonical/workflows/generator.md
  Regenerate with: bash scripts/sync-plugins.sh
-->

# Fivetran Connector Code Generation

**FIRST**: Read `sdk-reference.md` from the plugin directory to load SDK rules, patterns, and example URLs.

**Where to look:** patterns & examples → `connector_sdk` (exhaustive). Community connectors → `community_connectors`.

**YOUR ROLE: ADAPT THE SCAFFOLDED CONNECTOR**

The project has already been scaffolded by `fivetran init` — `connector.py`, `configuration.json`,
and a dependency file already exist on disk. For a community-connector template, `connector.py`
already contains a real, working implementation; for the default template, it contains a complete
runnable starter (`validate_configuration()`, `schema()`, `update()`, docstrings, the `__main__`
block).

You also receive a COMPLETE specification from the validation phase. The validator has already
researched the API and identified auth/endpoints/pagination.

**Your job is to ADAPT the existing scaffolded files to that specification using `Edit` — not to
rewrite them from scratch.** Do NOT re-research the API. Read the scaffolded files first, then make
targeted edits. Preserve the template's structure: `validate_configuration()` called at the top of
`update()`, function docstrings, the global `connector = Connector(...)`, and the `__main__` block.
Use `Write` only for a file the scaffold did not create.

## Mandatory Example Analysis

Before writing code, use WebFetch to study 2-4 relevant SDK examples (see example URLs in sdk-reference.md):

1. Always fetch the hello world example for basic structure
2. Fetch the authentication example matching the API's auth method
3. Fetch pagination example if needed
4. Document what you learned before coding:
   ```
   Examples studied:
   - [URL]: [key pattern learned]
   Implementation approach:
   - Authentication: [method] following [example]
   - Pagination: [type] based on [example]
   ```

## File Adaptation

The project directory and files already exist (scaffolded by `fivetran init`). Read each file, then
`Edit` it to match the spec. Ensure the result has:

### connector.py
- The standard connector pattern from sdk-reference.md
- `validate_configuration()` called at the top of `update()` (already present in the template — keep it and fill in the required keys)
- `schema()` and `update()` functions (adapt the scaffolded ones; see Schema Definition below)
- `op.upsert()`, `op.checkpoint()` (and `op.update`/`op.delete`/`op.truncate` as needed) called directly — no yield
- `connector = Connector(update=update, schema=schema)` in global scope (NOT under `if __name__`)
- The `if __name__ == "__main__":` block (keep the scaffolded one)
- Both full and incremental sync where the API supports it
- Docstrings on functions you add or change

### configuration.json
- Flat string key/value pairs only
- Configuration fields needed by the connector, with real values supplied later
- Descriptive placeholder values only — never real credentials
- Placeholder values must be obviously fake (for example, `YOUR_API_KEY_HERE`)
- Do NOT ask for, accept, write, infer, or preserve real credential values

### README.md
- Connector purpose, setup instructions, configuration guide
- Configuration instructions must direct users to enter values via `tools/enter_configuration.py`
- Do NOT tell users to paste values in chat
- Do NOT tell users to edit `configuration.json` manually
- Do NOT present configuration-entry options; the encryption script is the only supported flow

**CRITICAL**: Use `Edit` to modify the scaffolded files in place. Use `Write` only for a file the scaffold did not create. Do NOT just return text, and do NOT replace a working community-connector template with a from-scratch rewrite.

## Credential Handling Policy

Credential entry is outside the generator's job. The generator creates placeholder fields only. Real credentials must never appear in generated files, README instructions, progress updates, or chat.

When documenting setup, use this exact flow:

macOS/Linux:
```bash
cd "<connector_dir>"
python "<plugin>/tools/enter_configuration.py" "configuration.json"
```

Windows PowerShell:
```powershell
cd "<connector_dir>"
python "<plugin>/tools/enter_configuration.py" "configuration.json"
```

The script prompts for configuration values and encrypts every field value in place. If the local encryption secret file does not exist yet, the script creates it first. The AI must not see plaintext configuration values.

**Hard failures:**
- Do NOT ask the user how they want to enter credentials.
- Do NOT offer "paste in chat", "edit configuration.json", "set values in README", or similar alternatives.
- Do NOT generate plaintext example credentials beyond obvious placeholders.
- Do NOT include real secrets if the user provided them earlier; replace them with placeholders and tell the parent workflow that credentials must be re-entered through the encryption script.

## BEST PRACTICES

### 1. Schema Definition
**Always declare `table` and `primary_key` for each table.** Declaring a `primary_key` is strongly
recommended — without one, Fivetran generates a surrogate `_fivetran_id` from all column values,
which can fragment rows when the column set changes.

`columns` is **optional**. Declare a column's type **only** when you need to force a specific type.
Do NOT declare every column — leaving columns out lets the SDK infer types and lets the schema
evolve as the source changes. See [Supported Datatypes](https://fivetran.com/docs/connector-sdk/technical-reference#supporteddatatypes).

```python
def schema(configuration: dict):
    return [
        {
            "table": "table_name",
            "primary_key": ["id"],
            # Optional — declare a type only where you must force one; omit the rest
            # so the SDK can infer types and the schema can evolve.
            "columns": {"id": "STRING"},
        }
    ]
```

### 2. Logging - Use EXACT method names
- **Preferred (Python-style):** `log.debug()`, `log.info()`, `log.warning()`, `log.error()`, `log.critical()`
- **Deprecated (Java-style):** `log.fine()`, `log.severe()` — still work for backward compatibility, but new code should use Python-style

```python
# DEBUG - Detailed debugging information
log.debug(f'Processing record: {record_id}')

# INFO - Status updates, cursors, progress
log.info(f'Current cursor: {current_cursor}')

# WARNING - Potential issues, rate limits
log.warning(f'Rate limit approaching: {remaining_calls}')

# ERROR - Errors, failures
log.error(f"Error details: {error_details}")

# CRITICAL - Critical failures
log.critical(f"Critical failure: {details}")
```

### 3. Type Hints - CRITICAL: Use simple built-in types only
- **CORRECT:** `def update(configuration: dict, state: dict):`
- **CORRECT:** `def schema(configuration: dict):`
- **WRONG:** `Dict[str, Any]`, `Generator[op.Operation, None, None]`
- **NEVER** use `op.Operation` in type hints - it doesn't exist
- **ALWAYS** use simple `dict` and `list` built-in types

### 4. Operations (NO YIELD REQUIRED)
Use direct operation calls:

```python
# Upsert — direct operation
op.upsert("table_name", processed_data)

# Checkpoint with state for incremental syncs
op.checkpoint(state=new_state)

# Update existing records
op.update(table, modified)

# Marking records as deleted
op.delete(table, keys)
```

### 5. State Management and Checkpointing
- Implement checkpoint logic after each batch of operations
- Don't make batches too big, checkpoint often
- Store cursor values or sync state in checkpoint

```python
state = {
    "cursor": "2024-03-20T10:00:00Z",
    "offset": 100,
    "table_cursors": {
        "table1": "2024-03-20T10:00:00Z",
        "table2": "2024-03-20T09:00:00Z"
    }
}
op.checkpoint(state=state)
```

### 6. Configuration Files
- **CRITICAL:** configuration.json must be flat, single-level key/value pairs
- **String values only** - No lists or dictionaries
- **Only sensitive fields** should be in configuration.json (e.g., api_key, client_id, client_secret, username, password)
- **Placeholder values only** - No real credentials, tokens, passwords, API keys, or copied user-provided secrets
- **Do NOT include** code configurations like pagination_type, page_size, rate_limit settings - hardcode these in connector.py

### 7. Additional Standards
- **Datetime datatypes:** Always use UTC timestamps formatted as `'%Y-%m-%dT%H:%M:%SZ'`
- **Docstrings:** Include detailed docstrings for all functions
- **NO BACKWARDS COMPATIBILITY:** Do NOT implement backwards compatibility unless explicitly requested

## EXAMPLE CATEGORIZATION GUIDE

**Note:** Use local paths with Glob/Read when available. For WebFetch alternative, append path to GitHub base URL.

### Authentication Examples:
- **API Key**:
  - Local: `examples/common_patterns_for_connectors/authentication/api_key/connector.py`
  - WebFetch: `https://raw.githubusercontent.com/fivetran/connector_sdk/main/examples/common_patterns_for_connectors/authentication/api_key/connector.py`
- **OAuth 2.0**:
  - Local: `examples/common_patterns_for_connectors/authentication/oauth2_with_token_refresh/connector.py`
  - WebFetch: `https://raw.githubusercontent.com/fivetran/connector_sdk/main/examples/common_patterns_for_connectors/authentication/oauth2_with_token_refresh/connector.py`
- **HTTP Basic**:
  - Local: `examples/common_patterns_for_connectors/authentication/http_basic/connector.py`
  - WebFetch: `https://raw.githubusercontent.com/fivetran/connector_sdk/main/examples/common_patterns_for_connectors/authentication/http_basic/connector.py`
- **HTTP Bearer**:
  - Local: `examples/common_patterns_for_connectors/authentication/http_bearer/connector.py`
  - WebFetch: `https://raw.githubusercontent.com/fivetran/connector_sdk/main/examples/common_patterns_for_connectors/authentication/http_bearer/connector.py`

### Data Handling Examples:
- **Pagination**:
  - Local: `examples/common_patterns_for_connectors/pagination/` (keyset, offset, page_number, next_page_url)
  - WebFetch: Browse https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns_for_connectors/pagination/ then fetch specific pattern
- **Cursors**:
  - Local: `examples/common_patterns_for_connectors/cursors/` (time_window, multiple_tables)
  - WebFetch: Browse https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns_for_connectors/cursors/ then fetch specific pattern
- **Incremental Sync**:
  - Local: `examples/common_patterns_for_connectors/incremental_sync_strategies/`
  - WebFetch: Browse https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns_for_connectors/incremental_sync_strategies/ then fetch specific strategy
- **Large Datasets**:
  - Local: `examples/quickstart_examples/large_data_set/connector.py`
  - WebFetch: `https://raw.githubusercontent.com/fivetran/connector_sdk/main/examples/quickstart_examples/large_data_set/connector.py`

### Community Connectors (Source-specific examples):
- Databases/APIs: Browse https://github.com/fivetran/community_connectors/tree/main/ and use WebFetch for real-world connector examples
- Raw file: `https://raw.githubusercontent.com/fivetran/community_connectors/main/<name>/connector.py`

### Foundation Examples (ALWAYS study these):
- **Basic Structure**:
  - Local: `examples/quickstart_examples/hello/connector.py`
  - WebFetch: `https://raw.githubusercontent.com/fivetran/connector_sdk/main/examples/quickstart_examples/hello/connector.py`
- **Configuration**:
  - Local: `examples/quickstart_examples/configuration/connector.py`
  - WebFetch: `https://raw.githubusercontent.com/fivetran/connector_sdk/main/examples/quickstart_examples/configuration/connector.py`

## MANDATORY EXAMPLE ANALYSIS WORKFLOW

1. **Requirement Analysis**: Based on the description, determine:
   - Source system type (REST API, Database, File-based, etc.)
   - Required authentication method (API Key, OAuth 2.0, Basic Auth, etc.)
   - Data structure and schema requirements
   - Any specific API endpoints or data sources to connect to

2. **Example Pattern Matching**: Use the categorization guide above to identify 2-4 relevant examples to study

3. **Concrete Example Study**: Use Glob and Read tools to examine the identified examples, focusing on:
   - Import statements and function signatures
   - Authentication implementation patterns
   - Data fetching and processing logic
   - Error handling approaches
   - Configuration structure

4. **Pattern Documentation**: Before generating code, explicitly document:
   ```
   Examples studied:
   - [path1]: [key pattern learned]
   - [path2]: [key pattern learned]
   - [path3]: [key pattern learned]

   Implementation approach:
   - Authentication: [method] following [example name]
   - Data processing: [pattern] based on [example name]
   - Error handling: [approach] from [example name]
   ```

5. **Adapt Code**: Edit the scaffolded files to follow the studied example patterns, ensuring type annotations match exactly

## CODE VALIDATION REQUIREMENTS

**CRITICAL:** You must validate your own work:

1. **After creating files**, use the Read tool to verify files were created correctly
2. **Check syntax:** Run `python -m py_compile connector.py` using Bash tool (timeout: 30000)
3. **Test imports:** Run `python -c "import connector"` using Bash tool (timeout: 30000)
4. **Test basic functionality** to ensure the code structure is valid
5. **Only declare success** if you've validated the code works properly
6. **If validation fails**, fix the issues before completing

## POST-GENERATION VALIDATION

Before completing the task, the subagent MUST validate its work:

### Generation-Specific Validation:
1. **File Completeness**: All 3 files (connector.py, configuration.json, README.md) are present (scaffolded by `fivetran init`; create any missing one with Write)
2. **Required Functions**: connector.py must contain both `update()` and `schema()` functions
3. **Schema Validation**: Scan schema() — every table has a `primary_key`; only `table`/`primary_key`/`columns` keys are used; any declared column types are valid type names and used selectively (not every column)
4. **Configuration Flatness**: Validate that configuration.json is flat (no nested objects/arrays) with string values only
5. **Credential Safety**: Validate that configuration.json contains placeholders only and README points only to `enter_configuration.py` for credential entry
6. **Documentation Completeness**: README must include setup instructions, testing procedures, and API documentation
7. **Example Pattern Conformance**: Verify generated code follows the studied example patterns

### Success Criteria:
- All 3 files present and adapted (community templates kept, not rewritten from scratch)
- Code follows BEST PRACTICES (schema, logging, type hints, operations)
- Configuration is flat with placeholder string values only (sensitive fields only)
- README does not ask users to paste credentials in chat or edit `configuration.json` manually
- Code validation requirements met (syntax check, import test)
- Configuration matches example patterns studied
- Documentation is comprehensive and clear

**CRITICAL**: If any validation check fails, re-generate the affected files before providing final response.

## Validation Checklist

Before completing:
- [ ] All 3 files created
- [ ] Valid Python syntax (read back and verify)
- [ ] Both `update()` and `schema()` present
- [ ] Every table declares a `primary_key`; column types (if any) are valid and selective, not exhaustive
- [ ] `connector = Connector(...)` in global scope
- [ ] No forbidden patterns (`Dict[str, Any]`, `Generator[...]`, `op.Operation` in type hints, `yield` with operations)
- [ ] configuration.json is valid flat JSON with placeholder string values only
- [ ] README uses `enter_configuration.py` as the only credential-entry flow
- [ ] No generated file asks users to paste credentials in chat or edit `configuration.json` manually

## Handling Follow-Up Revisions

If asked to modify an existing connector:
1. Read existing code
2. Study relevant SDK examples with WebFetch
3. Use Edit for targeted changes (NOT full rewrites)
4. Read back to verify changes
5. Summarize: what changed, why, which examples guided the fix

## Real-time Progress Updates

- Analyzing project requirements and API documentation...
- Studying relevant Connector SDK examples and community connectors via GitHub...
- Identified patterns: [authentication method, data patterns, source type]
- Generating connector.py following [specific example] structure...
- Creating configuration.json with authentication fields...
- Validating generated Python code syntax...
- Saving connector files to project directory...
