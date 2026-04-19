---
name: build-connector
description: Build a new Fivetran connector from a description. Use when the user wants to create, generate, or scaffold a new Fivetran connector for an API or data source.
---

# Build a New Fivetran Connector

**FIRST**: Read `sdk-reference.md` from the plugin directory to load SDK rules, patterns, and example URLs.

You are building a complete Fivetran connector from the user's description.

This skill combines three workflows:
- **Phase 1** — validation/research (gather requirements)
- **Phase 3** — code generation
- **Phase 6** — auto-fix on test failure

Canonical workflow sources in this plugin: `validator.md`, `generator.md`, `fixer.md` (packaged with the plugin).

## Phase 1: Research & Validate Requirements

**IMPORTANT: Ask clarifying questions and WAIT for user answers before proceeding to code generation.**

Use web fetch to research the API documentation:

1. Extract any documentation URLs from the user's description
2. If docs are provided, fetch them and extract:
   - Authentication requirements (API keys, OAuth, Bearer tokens)
   - Available endpoints and their paths
   - Request/response formats and field names
   - Pagination patterns (offset, cursor, page number, next URL)
   - Rate limiting constraints
3. If NO docs are provided, ask the user for API documentation links before proceeding

After research, you MUST determine:
- **Authentication**: method, credential field names, header format
- **Endpoints**: full paths, HTTP methods, required params (for each table)
- **Data Structure**: table names, primary key fields, key response fields
- **Pagination**: type, page size param, how to detect last page
- **Sync Strategy**: determine from API capabilities (incremental if cursor field available, full refresh otherwise). Always implement both full historical import on first run AND incremental updates on subsequent runs when the API supports it. Do NOT ask the user about this.
- **Rate Limits**: requests per minute/second, recommended delay

### What YOU Determine vs. What to ASK

| Determine from API Docs | Ask the User |
|------------------------|--------------|
| Authentication method & header format | Which specific tables/resources to sync |
| Endpoint paths & HTTP methods | Specific filtering requirements |
| Pagination type & parameters | Priority of tables if too many |
| Rate limits | Clarification on vague descriptions |
| Response structure & primary keys | |
| Sync strategy (incremental vs full) | |

### Ask Clarifying Questions

Before generating code, present your findings and ask about anything unclear:

- "The GitHub API can sync repositories, issues, pull requests, commits, etc. Which do you want?"
- "Sync from a specific organization/repository, or all repos the user has access to?"
- "Include closed issues or only open ones?"

**STOP and WAIT for the user to answer** before proceeding to Phase 2.

This validation may take multiple rounds. Keep asking until you have all information needed.

**Skip validation**: If the user says "just use this", "skip validation", or "proceed as-is", accept the description and move on with reasonable defaults.

Do NOT guess about: which tables to sync, filtering criteria, or scope.

## Phase 2: Study SDK Examples

MANDATORY: Fetch 2-4 relevant SDK examples before writing code. See `sdk-reference.md` for example URLs.

1. Always fetch the hello world example for basic structure
2. Fetch the authentication example matching the API's auth method
3. Fetch a pagination example if needed
4. Document what you learned:
   ```
   Examples studied:
   - [URL]: [key pattern learned]
   Implementation approach:
   - Authentication: [method] following [example]
   - Pagination: [type] based on [example]
   ```

## Phase 3: Generate Connector Files

Create a project directory named after the connector (lowercase, underscores), then create:

### connector.py
- `from fivetran_connector_sdk import Connector, Operations as op, Logging as log`
- Implement `schema(configuration: dict)` with table names and primary keys only (no data types)
- Implement `update(configuration: dict, state: dict)` with data fetching, ops, and checkpoints
- Declare `connector = Connector(update=update, schema=schema)` in global scope
- Include `if __name__ == "__main__": connector.debug()`
- Use `log.info()`, `log.warning()`, `log.severe()` — NEVER `log.error()`
- Use simple type hints: `dict`, `list` — NEVER `Dict[str, Any]` or `Generator`

### configuration.json
- Flat, single-level key/value pairs
- ALL values must be strings
- Only sensitive/credential fields
- Descriptive placeholder values (e.g., `"your_api_key_here"`)

### README.md
- Connector purpose and functionality
- Setup instructions (how to get API credentials)
- Configuration guide
- Testing procedures

## Phase 4: Setup Environment

```bash
cd <project_directory>
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt fivetran_connector_sdk
```

## Phase 5: Enter Configuration & Test

**IMPORTANT: Never ask the user to paste credentials in chat or put them in configuration.json as plain text.**

Direct the user to use the secure configuration tool in a separate terminal:

```
python <plugin_dir>/tools/enter_configuration.py configuration.json
```

This encrypts credentials at rest so the AI cannot see them.

After the user confirms credentials are entered, run the connector:

```bash
python <plugin_dir>/tools/run_connector.py <project_directory>
```

This decrypts the config in memory and passes it via named pipe — plaintext credentials never touch disk.

Check results:
```bash
python -c "import duckdb; conn = duckdb.connect('files/warehouse.db')
tables = conn.execute(\"SELECT table_name FROM information_schema.tables WHERE table_schema = 'tester'\").fetchall()
for (t,) in tables: print(f'{t}: {conn.execute(f\"SELECT COUNT(*) FROM tester.{t}\").fetchone()[0]} rows')"
```

Report: tables synced, row counts, any errors.

## Phase 6: Auto-Fix on Failure

If the test fails:
1. Read error output carefully
2. Classify the error:
   - **INFRA error** (network, JVM, SDK internal): Explain the infra issue, do NOT change code
   - **FIRST_RUN error** (connector never succeeded — likely credentials/config): Guide user to verify config, do NOT change code
   - **CODE error** (syntax, logic, SDK misuse): Fix the connector code automatically
   - **TOOL error** (run_connector.py fails): Report to user, do NOT modify plugin tools
3. For CODE errors:
   - Study relevant SDK examples for the correct pattern
   - Apply targeted fixes to the connector code only
   - Re-test after fixing

**IMPORTANT**: Never modify plugin tools. Only fix the user's connector code.

## Validation Checklist

Before declaring success:
- [ ] All 3 files created (connector.py, configuration.json, README.md)
- [ ] connector.py has valid Python syntax
- [ ] Both `update()` and `schema()` functions present
- [ ] `connector = Connector(update=update, schema=schema)` in global scope
- [ ] No forbidden patterns (`log.error()`, `Dict[str, Any]`, `Generator`)
- [ ] configuration.json is valid flat JSON with string values only
- [ ] Virtual environment created and dependencies installed
- [ ] Test ran (or user informed about credential setup needed)
