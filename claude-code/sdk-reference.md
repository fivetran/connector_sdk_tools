<!--
  GENERATED FILE — DO NOT EDIT.
  Canonical source: canonical/sdk-reference.md
  Regenerate with: bash scripts/sync-plugins.sh
-->

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
| `fivetran init` | Create new project from the default template |
| `fivetran init --template connectors/<name>` | Start from a community connector |
| `fivetran debug` | Test locally, produces `warehouse.db` (DuckDB) |
| `fivetran package` | Build a deployable ZIP without uploading |
| `fivetran deploy --api-key <key> --destination <dest> --connection <name>` | Deploy to Fivetran |
| `fivetran deploy --python <ver>` | Deploy on a specific Python version (default: 3.13) |
| `fivetran deploy --hybrid-deployment-agent-id <id>` | Deploy via a Hybrid Deployment agent |
| `fivetran reset --force` | Reset local state (clear warehouse.db) |
| `fivetran version` | Print the installed SDK version |

**Complete CLI reference**: https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-commands

**Note**: `fivetran init` without `--template` creates a complete, working connector — not empty boilerplate.

**`fivetran deploy` arguments**: authentication is required via `--api-key` or the inherited `FIVETRAN_API_KEY` environment variable; `--connection` is required; `--destination` is optional only if your account has a single destination. The connection name must begin with `_` or a lowercase letter and contain only `_`, lowercase letters, or digits. `--template` routing: `connectors/<name>` pulls from `community_connectors`, `examples/<path>` from `connector_sdk`, and no flag uses the default `_template_connector`.

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

### Schema Definition

- **Always declare `table` and `primary_key`** for each table. Without a primary key, Fivetran
  creates a surrogate `_fivetran_id` column hashed from all values, which can fragment rows.
- `columns` is **optional**. Declare a column's type **only** when you need to force a specific
  type — do **not** declare every column. Leaving columns out lets the SDK infer types and allows
  the schema to evolve as the source changes.
- Valid schema keys: `table`, `primary_key`, `columns` (any other key is invalid).
- Valid data types: `BOOLEAN`, `SHORT`, `INT`, `LONG`, `DECIMAL`, `FLOAT`, `DOUBLE`, `NAIVE_DATE`,
  `NAIVE_DATETIME`, `UTC_DATETIME`, `BINARY`, `XML`, `STRING`, `JSON`.
- See [Supported Datatypes](https://fivetran.com/docs/connector-sdk/technical-reference#supporteddatatypes)

```python
def schema(configuration: dict):
    return [
        {
            "table": "table_name",
            "primary_key": ["id"],
            # Optional: declare a type only where you need to force one.
            # Omit columns you want the SDK to infer (allows schema evolution).
            "columns": {"id": "STRING"},
        }
    ]
```

### Operations

Call operations directly.

| Operation | Description |
|-----------|-------------|
| `op.upsert(table="t", data=record)` | Insert or update a record by primary key |
| `op.update(table="t", modified=record)` | Update an existing record only (no new rows) |
| `op.delete(table="t", keys={"id": "123"})` | Soft-delete a record (`_fivetran_deleted = TRUE`) |
| `op.truncate(table="t")` | Soft-delete all rows synced before this call; flushed at the next checkpoint |
| `op.checkpoint(state=state)` | Save sync progress (and flush buffered data to the destination) |

### configuration.json Rules
- **Flat key/value pairs only** — no nested objects or arrays
- **All values must be strings**
- **Source credentials and user-specific settings** (api_key, client_secret, password, zip_codes, etc.)
- Preserve authorized local values; keep populated configuration out of version control
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

## Configuration entry

Reuse existing local configuration; collect only missing values. Configuration is
an ordinary flat `configuration.json` object with string values, not necessarily
secrets. Preserve values supplied by the user, especially settings they explicitly
identify as non-sensitive; the agent may fill them into the file directly. Do not
invent production settings or require the user to re-enter values already supplied.

For a deployed connector with missing local values, attempt supported read-only
configuration retrieval first. Keep recovered values out of tool output and logs;
never treat a masked value as usable configuration. Check for masking/redaction
before copying API values into a runnable or deployable file. Placeholders such as
`******` mean the value is unavailable; a test using them does not establish that
the production configuration is invalid.

Preserve existing production configuration during code repairs unless the user
authorizes a change. Discover supported update behavior from installed CLI help
or documentation before concluding that unavailable values block deployment.
Keep sample test inputs separate from production settings; success with sample
values does not validate the actual production configuration.

When values still need collecting, try the project's `fivetran configuration`.
It uses the connector's setup form and saves ordinary JSON; it does not download
production configuration. Preserve existing files and respect overwrite prompts.
If the CLI reports that no setup form is defined, ask whether the user wants to add
one. Only implement that change with their agreement, using the installed SDK's
configuration-form API and examples, then run `fivetran configuration` again.
Otherwise fill `configuration.json` with supplied or retrievable values and ask
only for unresolved fields. Do not require a setup form for a code repair.

The SDK form is interactive. Use the harness's interactive terminal if available;
otherwise give the user the command only if they have access to that project
and a terminal. In a browser-hosted harness, perform workspace changes with the
available tools and ask only for missing information or decisions. If sensitive
values are required and no secure entry flow is available, explain that limitation
rather than directing the user to an inaccessible server terminal. EOF, missing stdin, setup or test errors, or dependency failures do not prove
that a setup form is absent. Report the actual error and resolve it appropriately.
Do not ask users to paste secrets into chat; use the form or have the user enter
secret values in `configuration.json` using their own local editor or terminal.
User-supplied values may be written as requested without repeating
them in the response. Keep configuration out of version control and avoid printing
populated configuration during inspection or debugging.

Custom encryption and `csdk_master_secret` are not prerequisites. Do not send users
to `enter_configuration.py` as the default flow or replace their existing key.
The existing runner also accepts previously encrypted fields; if those cannot be
decrypted, explain the limitation and obtain replacement values through the flow
above rather than silently changing keys or discarding usable local values.

## Gotchas

- **`requests` is bundled** — don't add it to requirements.txt
- **`warehouse.db` is DuckDB, not SQLite** — use `duckdb.connect('files/warehouse.db')`, tables are in the `tester` schema
- **`fivetran reset` prompts for confirmation** — use `--force` in scripts/agents
- **Datetime fields** — always use UTC, format as `'%Y-%m-%dT%H:%M:%SZ'`
- **Never use `exit()`** — use `raise RuntimeError(...)` instead
- **`connector = Connector(...)`** must be in global scope, NOT under `if __name__`
- **Encrypted configuration values** — if configuration.json contains inline `ENCRYPTED:v1:<key_id>:local-fernet:` values, this is normal; decryption happens at runtime.

## Connector Discovery

**Where to look:** patterns & examples → `connector_sdk` (exhaustive). Community connectors → `community_connectors`.

There are **two source repositories** — always consider both before building from scratch:

| Repository | Use for | `--template` prefix |
|------------|---------|---------------------|
| **Examples** — https://github.com/fivetran/connector_sdk/tree/main/ | Quickstart examples (`examples/quickstart_examples/`) and reusable building blocks (`examples/common_patterns_for_connectors/`) — auth, pagination, sync strategy, error handling | `examples/<path>` |
| **Community connectors** — https://github.com/fivetran/community_connectors/ | Source-specific, ready-to-use connectors for real APIs and databases | `connectors/<name>` |

Before building a new connector:
1. Check the **community connectors** repo for an exact/fuzzy match for the source.
2. Identify which **examples** (common patterns) apply based on auth, pagination, and sync style — these apply to every connector regardless of source.
3. Start from the best match with `fivetran init --template <prefix>` (`connectors/<name>` resolves to `community_connectors`; `examples/<path>` resolves to `connector_sdk`; no flag uses the default `_template_connector`).

## SDK Example URLs

All example URLs below live in the **examples** repo (`fivetran/connector_sdk`).
Community connectors live in `fivetran/community_connectors`
(raw: `https://raw.githubusercontent.com/fivetran/community_connectors/main/<name>/connector.py`).

### Authentication
- API Key: `https://raw.githubusercontent.com/fivetran/connector_sdk/main/examples/common_patterns_for_connectors/authentication/api_key/connector.py`
- OAuth2: `https://raw.githubusercontent.com/fivetran/connector_sdk/main/examples/common_patterns_for_connectors/authentication/oauth2_with_token_refresh/connector.py`
- HTTP Basic: `https://raw.githubusercontent.com/fivetran/connector_sdk/main/examples/common_patterns_for_connectors/authentication/http_basic/connector.py`
- HTTP Bearer: `https://raw.githubusercontent.com/fivetran/connector_sdk/main/examples/common_patterns_for_connectors/authentication/http_bearer/connector.py`
- Session Token: `https://raw.githubusercontent.com/fivetran/connector_sdk/main/examples/common_patterns_for_connectors/authentication/session_token/connector.py`
- Certificate: `https://raw.githubusercontent.com/fivetran/connector_sdk/main/examples/common_patterns_for_connectors/authentication/certificate/connector.py`

### Pagination
- Browse: `https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns_for_connectors/pagination/`

### Incremental Sync
- Browse: `https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns_for_connectors/incremental_sync_strategies/`

### Cursors
- Browse: `https://github.com/fivetran/connector_sdk/tree/main/examples/common_patterns_for_connectors/cursors/`

### Foundation
- Hello World: `https://raw.githubusercontent.com/fivetran/connector_sdk/main/examples/quickstart_examples/hello/connector.py`
- Configuration: `https://raw.githubusercontent.com/fivetran/connector_sdk/main/examples/quickstart_examples/configuration/connector.py`
- Large Dataset: `https://raw.githubusercontent.com/fivetran/connector_sdk/main/examples/quickstart_examples/large_data_set/connector.py`

## Reference Documentation
- [Connector SDK Overview](https://fivetran.com/docs/connector-sdk)
- [Technical Reference](https://fivetran.com/docs/connector-sdk/technical-reference)
- [Supported Datatypes](https://fivetran.com/docs/connector-sdk/technical-reference#supporteddatatypes)
- [Best Practices](https://fivetran.com/docs/connector-sdk/best-practices)
- [SDK Repository](https://github.com/fivetran/connector_sdk)
