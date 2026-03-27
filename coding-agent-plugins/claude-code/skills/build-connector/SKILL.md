---
description: Build a new Fivetran connector from a description. Use when the user wants to create, generate, or scaffold a new connector.
argument-hint: "Describe the connector (e.g., 'Stripe API connector for payments and customers')"
---

> **Context**: This plugin is for the Fivetran Connector SDK (CSDK). "CSDK" is shorthand for "Connector SDK".

# Build a New Fivetran Connector

You are building a complete Fivetran connector from the user's description: `$ARGUMENTS`

Follow this workflow strictly:

## Phase 1: Research & Validate Requirements

**IMPORTANT: You MUST ask clarifying questions and WAIT for user answers before proceeding to code generation.**

Use WebFetch to research the API documentation:

1. Extract any documentation URLs from the user's description
2. If docs are provided, use WebFetch to understand:
   - Authentication requirements (API keys, OAuth, Bearer tokens)
   - Available endpoints and their paths
   - Request/response formats and field names
   - Pagination patterns (offset, cursor, page number, next URL)
   - Rate limiting constraints
3. If NO docs are provided, ask the user for API documentation links before proceeding

After research, you MUST determine ALL of the following:
- **Authentication**: Method, credential field names, header format
- **Endpoints**: Full paths, HTTP methods, required params (for each table)
- **Data Structure**: Table names, primary key fields, key response fields
- **Pagination**: Type, page size param, how to detect last page
- **Sync Strategy**: Research the API docs to determine if incremental sync is supported (e.g., `since`, `updated_at`, `modified_after` parameters). **Always implement both**: full historical import on first run AND incremental updates on subsequent runs (if the API supports it). Do NOT ask the user about this.
- **Rate Limits**: Requests per minute/second, recommended delay
- **Configuration Fields**: What non-credential config is needed (e.g., org name, repo name, date range)

### Ask Clarifying Questions

Before generating code, present your findings and ask about anything unclear or ambiguous:

Example questions you might need to ask:
- "The GitHub API can sync repositories, issues, pull requests, commits, etc. Which of these do you want to include?"
- "Do you want to sync data from a specific organization/repository, or all repos the user has access to?"
- "Should I include closed issues or only open ones?"

**STOP and WAIT for the user to answer your questions before proceeding to Phase 2.**

This validation may take **multiple rounds** - keep asking questions until you have all the information needed to build the connector. After each user response, check if you have enough detail. If not, ask follow-up questions.

**Skip validation**: If the user says "just use this" or "skip validation" or "proceed as-is", accept the description and move to Phase 2 immediately, making reasonable default choices.

Do NOT guess or make assumptions about:
- Which specific data/tables to sync
- Filtering criteria (date ranges, statuses, etc.)
- Scope (specific resources vs. all accessible resources)

## Phase 2: Study SDK Examples

MANDATORY: Use WebFetch to study relevant examples from GitHub before writing code.

1. Always fetch the basic pattern first:
   `https://raw.githubusercontent.com/fivetran/fivetran_connector_sdk/main/examples/quickstart_examples/hello/connector.py`

2. Fetch authentication example matching the API's auth method:
   - API Key: `https://raw.githubusercontent.com/fivetran/fivetran_connector_sdk/main/examples/common_patterns_for_connectors/authentication/api_key/connector.py`
   - OAuth: `https://raw.githubusercontent.com/fivetran/fivetran_connector_sdk/main/examples/common_patterns_for_connectors/authentication/oauth2_with_token_refresh/connector.py`
   - HTTP Basic: `https://raw.githubusercontent.com/fivetran/fivetran_connector_sdk/main/examples/common_patterns_for_connectors/authentication/http_basic/connector.py`
   - HTTP Bearer: `https://raw.githubusercontent.com/fivetran/fivetran_connector_sdk/main/examples/common_patterns_for_connectors/authentication/http_bearer/connector.py`

3. Fetch pagination example if needed:
   - Browse `https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/pagination/`

4. Document what you learned before coding:
   ```
   Examples studied:
   - [URL]: [key pattern learned]
   Implementation approach:
   - Authentication: [method] following [example]
   - Pagination: [type] based on [example]
   ```

## Phase 3: Generate Connector Files

Create a project directory named after the connector (lowercase, underscores), then create these files:

### connector.py
- Use `from fivetran_connector_sdk import Connector, Operations as op, Logging as log`
- Implement `schema(configuration: dict)` with table names and primary keys only (no data types)
- Implement `update(configuration: dict, state: dict)` with data fetching, ops, and checkpoints
- Declare `connector = Connector(update=update, schema=schema)` in global scope
- Include `if __name__ == "__main__": connector.debug()`
- Use `log.info()`, `log.warning()`, `log.severe()` — NEVER `log.error()`
- Use simple type hints: `dict`, `list` — NEVER `Dict[str, Any]` or `Generator`

### configuration.json
- Flat, single-level key/value pairs
- ALL values must be strings
- Only include sensitive/credential fields
- Use descriptive placeholder values (e.g., `"your_api_key_here"`)

### README.md
- Connector purpose and functionality
- Setup instructions (how to get API credentials)
- Configuration guide (what each field means)
- Testing procedures

## Phase 4: Setup Environment

Run these commands:
```bash
cd <project_directory>
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt fivetran_connector_sdk
```

## Phase 5: Enter Configuration & Test

**IMPORTANT: Never ask the user to provide credentials directly in the chat or paste them into configuration.json as plain text.**

Tell the user to enter their credentials securely using the configuration tool in a **separate terminal**:

```
To enter your API credentials securely, run this in a separate terminal:

  python /path/to/coding-agent-plugins/claude-code/tools/enter_configuration.py configuration.json

This encrypts your credentials so the AI cannot see them.
Do NOT paste credentials directly into configuration.json or this chat.
```

After the user confirms they've entered their credentials, run the connector using the secure runner:

```bash
python /path/to/coding-agent-plugins/claude-code/tools/run_connector.py <project_directory>
```

This decrypts the config in memory and passes it to `fivetran debug` via named pipe - credentials never touch disk in plaintext.

Check results:
   ```bash
   python -c "import duckdb; conn = duckdb.connect('warehouse.db'); print(conn.execute('SHOW TABLES').fetchall()); [print(f'{t[0]}: {conn.execute(f\"SELECT COUNT(*) FROM {t[0]}\").fetchone()[0]} rows') for t in conn.execute('SHOW TABLES').fetchall()]"
   ```
4. Report results: tables synced, row counts, any errors

## Phase 6: Auto-Fix (if test fails)

If testing fails:
1. Read the error output carefully
2. Classify the error:
   - **INFRA error** (network, JVM, SDK internal errors): Explain the infrastructure issue
   - **FIRST_RUN error** (connector never succeeded - likely credentials/config): Guide user to verify config
   - **CODE error** (syntax, logic, SDK usage): Fix the connector code automatically
   - **TOOL error** (run_connector.py, enter_configuration.py fails): Report to user, do NOT fix
3. For CODE errors:
   - Study relevant SDK examples for the correct pattern
   - Use Edit tool to apply targeted fixes to the **connector code only**
   - Re-test after fixing

**IMPORTANT:** Never modify plugin tools (anything under `coding-agent-plugins/`). Only fix the user's connector code.

## Validation Checklist

Before declaring success, verify:
- [ ] All 3 files created (connector.py, configuration.json, README.md)
- [ ] connector.py has valid Python syntax
- [ ] Both `update()` and `schema()` functions present
- [ ] `connector = Connector(update=update, schema=schema)` in global scope
- [ ] No forbidden patterns (`log.error()`, `Dict[str, Any]`, `Generator`)
- [ ] configuration.json is valid flat JSON with string values only
- [ ] Virtual environment created and dependencies installed
- [ ] Test ran (or user informed about credential setup needed)
