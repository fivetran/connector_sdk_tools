<!--
  Fivetran Connector SDK — shared technical reference.
  
  This is the single source of truth for SDK rules, patterns, and constraints.
  Referenced by:
    - AGENTS.md (content inlined for non-Claude agents)
    - claude-code/CLAUDE.md (main conversation context)
    - claude-code/agents/*.md (subagents read this file on first turn)
-->

# Fivetran Connector SDK Reference

## CLI Quick Reference

| Command | Description |
|---------|-------------|
| `fivetran init` | Create new project from template |
| `fivetran init --template connectors/<name>` | Start from community connector |
| `fivetran debug` | Test locally, produces `warehouse.db` (DuckDB) |
| `fivetran package` | Build a deployable ZIP without uploading |
| `fivetran deploy` | Package and deploy to Fivetran |
| `fivetran deploy --python <ver>` | Deploy on a specific Python version (default: 3.13) |
| `fivetran deploy --hybrid-deployment-agent-id <id>` | Deploy via a Hybrid Deployment agent |
| `fivetran reset --force` | Reset local state (clear warehouse.db) |
| `fivetran version` | Print the installed SDK version |

**Complete CLI reference**: https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-commands

**Note**: `fivetran init` without `--template` creates a complete, working connector — not empty boilerplate.

## Runtime Environment

- **Memory:** 1 GB RAM
- **CPU:** 0.5 vCPUs
- **Python Versions:** 3.10.18, 3.11.13, 3.12.11, **3.13.7 (default)**, 3.14.0
  - Specify a non-default version with `fivetran deploy --python <version>`
  - Check https://fivetran.com/docs/connector-sdk/technical-reference for latest
- **Pre-installed Packages:** `requests`, `fivetran_connector_sdk`

## Standard Connector Pattern

```python
from fivetran_connector_sdk import Connector, Logging as log, Operations as op

def schema(configuration: dict):
    return [
        {"table": "my_table", "primary_key": ["id"]}
    ]

def update(configuration: dict, state: dict):
    data = fetch_data(configuration)
    for record in data:
        op.upsert(table="my_table", data=record)
    op.checkpoint(state=state)

connector = Connector(update=update, schema=schema)

if __name__ == "__main__":
    connector.debug()
```

## Critical Rules

### Logging — Use EXACT Method Names

- **Preferred (Python-style):** `log.debug()`, `log.info()`, `log.warning()`, `log.error()`, `log.critical()`
- **Deprecated (Java-style):** `log.fine()`, `log.severe()` — still work for backward compatibility, but new code should use the Python-style methods

| Level | Use | Production behavior |
|-------|-----|-------------------|
| `log.debug()` | Debug detail | Not emitted |
| `log.info()` | Status updates, progress | Rate-limited to 1500/min |
| `log.warning()` | Retries, non-critical issues | Always emitted |
| `log.error()` | Errors before raising | Always emitted |
| `log.critical()` | Critical failures | Always emitted |

Never log per-record. Log at milestones (per table, every 250K records).

### Type Hints — Simple Built-in Types Only
- **CORRECT:** `def update(configuration: dict, state: dict):`
- **WRONG:** `Dict[str, Any]`, `Generator[op.Operation, None, None]`
- **NEVER** use `op.Operation` in type hints — it doesn't exist
- **ALWAYS** use `dict` and `list`, not typing module imports

### Schema Definition — No Data Types
- Only table names and primary keys
- Data types are auto-detected by the SDK
- See [Supported Datatypes](https://fivetran.com/docs/connector-sdk/technical-reference#supporteddatatypes)

```python
def schema(configuration: dict):
    return [
        {"table": "table_name", "primary_key": ["key"]}
    ]
```

### Operations

Call operations directly.

| Operation | Description |
|-----------|-------------|
| `op.upsert(table="t", data=record)` | Insert or update a record |
| `op.update(table="t", modified=record)` | Update existing record only |
| `op.delete(table="t", keys={"id": "123"})` | Delete a record |
| `op.checkpoint(state=state)` | Save sync progress |

### configuration.json Rules
- **Flat key/value pairs only** — no nested objects or arrays
- **All values must be strings**
- **Only sensitive fields** (api_key, client_secret, password, etc.)
- **Do NOT include** code settings (pagination_type, page_size) — hardcode in connector.py
- Multiple items (repos, accounts) = separate connector deployments, NOT array values

### Dependency Declaration
- Use `requirements.txt` (traditional) or `pyproject.toml` (added in SDK v2.8.1) — pick one
- Explicit versions for all dependencies
- Do NOT include `requests` or `fivetran_connector_sdk` (pre-installed)
- Use `.gitignore` to exclude files from deployment (replaces the older `.ftignore`)

## Advanced Patterns

### Retry Logic

All HTTP requests should retry on transient failures:

```python
for attempt in range(1, 4):
    try:
        r = session.get(url, timeout=120)
        if r.status_code == 429:
            if attempt == 3:
                log.error(f"Rate limited after 3 attempts: {url}")
                raise RuntimeError(f"HTTP 429: {url}")
            retry_after = int(r.headers.get("Retry-After", 60))
            log.warning(f"Rate limited, retrying in {retry_after}s")
            time.sleep(retry_after)
            continue
        if r.status_code >= 500:
            if attempt == 3:
                log.error(f"HTTP {r.status_code} after 3 attempts: {url}")
                raise RuntimeError(f"HTTP {r.status_code}: {url}")
            log.warning(f"HTTP {r.status_code}, attempt {attempt}/3, retrying in 30s")
            time.sleep(30)
            continue
        if r.status_code >= 400:
            log.error(f"HTTP {r.status_code}: {url}")
            raise RuntimeError(f"HTTP {r.status_code}: {url}")
        return r
    except (requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.ChunkedEncodingError) as e:
        if attempt == 3:
            log.error(f"Failed after 3 attempts: {url}", e)
            raise
        log.warning(f"Attempt {attempt}/3, retrying in 30s")
        time.sleep(30)
```

### Streaming Pagination

For large datasets, use generator pagination to keep memory flat:

```python
def _paginate(session, endpoint, per_page=500):
    url = f"{BASE_URL}/{endpoint}?per_page={per_page}"
    total = 0
    while url:
        r = _request_with_retry(session, url)
        records = r.json()
        yield from records
        total += len(records)
        url = _next_url(r)
    log.info(f"[{endpoint}] complete: {total:,} records")

for record in _paginate(session, "users"):
    op.upsert(table="users", data=record)
```

### State Management

- State holds cursors and optional backfill progress
- State file must be under 10MB
- Checkpoint every ~10 minutes for long operations, no more than once per minute

Per-entity checkpointing for multi-table syncs:

```python
def update(configuration, state):
    session = create_session(configuration)
    last_sync = state.get("last_sync_timestamp")
    backfill = state.get("backfill", {})

    for entity in ["users", "orders", "products"]:
        if backfill.get(entity) == "done":
            continue
        sync_entity(session, entity, last_sync)
        backfill[entity] = "done"
        state["backfill"] = backfill
        op.checkpoint(state=state)

    state["last_sync_timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    state.pop("backfill", None)
    op.checkpoint(state=state)
```

## Gotchas

- **`requests` is bundled** — don't add it to requirements.txt
- **`warehouse.db` is DuckDB, not SQLite** — use `duckdb.connect('files/warehouse.db')`, tables are in the `tester` schema
- **`fivetran reset` prompts for confirmation** — use `--force` in scripts/agents
- **Datetime fields** — always use UTC, format as `'%Y-%m-%dT%H:%M:%SZ'`
- **Never use `exit()`** — use `raise RuntimeError(...)` instead
- **`connector = Connector(...)`** must be in global scope, NOT under `if __name__`
- **Encrypted config** — if configuration.json contains a top-level `encrypted` field, this is normal; decryption happens at runtime. Legacy configs that start with `ENCRYPTED:` are also supported.

## Connector Discovery

Before building a new connector, check for existing starting points:
1. [Community connectors](https://github.com/fivetran/fivetran_connector_sdk/tree/main/connectors/)
2. [Common patterns](https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/)
3. Start with the best match using `fivetran init --template`

## SDK Example URLs

### Authentication
- API Key: `https://raw.githubusercontent.com/fivetran/fivetran_connector_sdk/main/examples/common_patterns_for_connectors/authentication/api_key/connector.py`
- OAuth2: `https://raw.githubusercontent.com/fivetran/fivetran_connector_sdk/main/examples/common_patterns_for_connectors/authentication/oauth2_with_token_refresh/connector.py`
- HTTP Basic: `https://raw.githubusercontent.com/fivetran/fivetran_connector_sdk/main/examples/common_patterns_for_connectors/authentication/http_basic/connector.py`
- HTTP Bearer: `https://raw.githubusercontent.com/fivetran/fivetran_connector_sdk/main/examples/common_patterns_for_connectors/authentication/http_bearer/connector.py`
- Session Token: `https://raw.githubusercontent.com/fivetran/fivetran_connector_sdk/main/examples/common_patterns_for_connectors/authentication/session_token/connector.py`
- Certificate: `https://raw.githubusercontent.com/fivetran/fivetran_connector_sdk/main/examples/common_patterns_for_connectors/authentication/certificate/connector.py`

### Pagination
- Browse: `https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/pagination/`

### Incremental Sync
- Browse: `https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/incremental_sync_strategies/`

### Cursors
- Browse: `https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/cursors/`

### Foundation
- Hello World: `https://raw.githubusercontent.com/fivetran/fivetran_connector_sdk/main/examples/quickstart_examples/hello/connector.py`
- Configuration: `https://raw.githubusercontent.com/fivetran/fivetran_connector_sdk/main/examples/quickstart_examples/configuration/connector.py`
- Large Dataset: `https://raw.githubusercontent.com/fivetran/fivetran_connector_sdk/main/examples/quickstart_examples/large_data_set/connector.py`

## Reference Documentation
- [Connector SDK Overview](https://fivetran.com/docs/connector-sdk)
- [Technical Reference](https://fivetran.com/docs/connector-sdk/technical-reference)
- [Supported Datatypes](https://fivetran.com/docs/connector-sdk/technical-reference#supporteddatatypes)
- [Best Practices](https://fivetran.com/docs/connector-sdk/best-practices)
- [SDK Repository](https://github.com/fivetran/fivetran_connector_sdk)
