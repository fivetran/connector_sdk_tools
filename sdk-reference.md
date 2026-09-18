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

Never log per-record — pick a milestone that fits what the connector is actually syncing, so a
long sync never goes silent long enough to look stuck:
- **By record count**, for high-volume single-entity syncs: e.g., every 250K records.
- **By entity/table**, for multi-entity syncs: log when starting and finishing each
  table/entity/account, not only at the very end.
- **By elapsed time**, for slow or unpredictable-volume calls (e.g., paginated API calls, large
  file downloads): log progress at least every minute or two of a long-running operation, even
  if no natural record/entity boundary has been hit yet.

Combine these where useful (e.g., "table X: 250K records synced, 3 tables remaining").

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
| `op.error(message="...", trace=None)` | Fail the sync immediately with a custom, dashboard-visible message (title: **Connector SDK Code Error**). Only one per sync — code stops running after the call. |
| `op.warning(message="...")` | Surface a non-critical, dashboard-visible warning without stopping the sync. Max 10 per sync; extras are dropped. |

**`op.error()`/`op.warning()` vs. `log.error()`/`log.warning()`:** logging methods write to sync
logs only — they do **not** create a dashboard alert or affect the sync outcome. Use
`op.error()`/`op.warning()` (optionally alongside logging) whenever the issue should be visible
to the user on the Fivetran dashboard, not just in logs.

### Error Handling — Choose the Right Response

| Pattern | When | How |
|---------|------|-----|
| **Retry** | Rate limits (HTTP 429), transient 5xx errors, network timeouts | Exponential backoff; honor `Retry-After` if present |
| **Warn and continue** | Part of the sync fails but the rest still delivers useful, correct data (one endpoint down, a few malformed rows, optional enrichment unavailable) | Call `op.warning(message)` so users know data was skipped, then continue |
| **Fail fast** | Invalid credentials (401/403), bad request (4xx other than 429), missing/invalid configuration, source data that breaks required assumptions | `raise RuntimeError(...)` (dashboard title: **Python code throwing error**) or call `op.error(message, trace=...)` for a custom dashboard message |

Fail fast for configuration problems **before** making source calls, inside `update()`. Never
silently drop data that should have failed or warned the user.

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

### Setup Form (`configuration_form`)

Use a setup form to collect configuration values in the Fivetran dashboard instead of requiring
users to provide all values through `configuration.json`. Field values are stored securely and
passed to `schema(configuration)` and `update(configuration, state)` at runtime through the
`configuration` dictionary, same as manually created `configuration.json` values.

The setup form is optional — connectors that don't define one can continue to use a manually
created `configuration.json` file. Define one when your connector needs users to provide
credentials or connection-specific settings during connection setup, want defined field
labels/descriptions/required fields/placeholders/options, want custom setup tests run before
users save and test the connection, or want to generate a local `configuration.json` from the
same fields for testing.

```python
from fivetran_connector_sdk import Connector, ConfigurationForm, Test, form_field

def configuration_form():
    form = ConfigurationForm()
    form.add_field(form_field.TextField(
        name="api_key",            # written to configuration.json; passed via `configuration` dict
        label="API Key",
        field_type=form_field.TextField.password,  # or .plain_text (default)
        required=True,
    ))
    form.add_test(label="Test connection", func=connection_test)
    return form

def connection_test(configuration: dict):
    test = Test()
    if not configuration.get("api_key"):
        return test.failure("API key is required.")
    return test.success()

connector = Connector(
    update=update,  # required; add schema=schema if you define a schema
    configuration_form=configuration_form,
)
```

- **Field types:** `form_field.TextField` (`field_type=form_field.TextField.plain_text` for
  visible input such as host names/URLs/usernames/IDs, or `.password` for secrets — masked),
  `form_field.DropdownField` (fixed list of `form_field.DropdownFieldParam(value=..., label=...,
  description=...)` options; values are converted to strings and stored as such),
  `form_field.ToggleField` (boolean on/off settings). Values collected by `fivetran configuration`
  are written to `configuration.json` as strings (e.g. toggles as `"true"`/`"false"`).
- **Setup tests:** register with `form.add_test(label=..., func=...)`; the function takes one
  `configuration: dict` argument and returns `Test().success()` or `Test().failure("message")`.
  Fivetran runs registered setup tests when users save and test the connection; run them locally
  with `fivetran configuration --test`.
- **`fivetran configuration`** interactively collects values from the setup form fields and
  writes them to `configuration.json` (project directory by default; overwrites an existing file
  only after confirmation). Requires a connector that defines `configuration_form` — otherwise the
  command exits without generating `configuration.json`. Password field values are stored
  encrypted by default (`fivetran_encrypted:` prefix, decrypted automatically by Fivetran); use
  `--disable-encryption` to store them as plaintext instead — not recommended when working with
  AI or in shared environments. `--test` always attempts to decrypt encrypted values regardless
  of `--disable-encryption`, and warns if it finds unencrypted password values.
- **Deployment:** packaging/deploying a connector includes the serialized setup form metadata in
  the package so Fivetran can render the form for the connection. You can still deploy with
  `--configuration configuration.json`; those values are stored securely and can pre-populate or
  update the connection's configuration — for an existing connection, omitting `--configuration`
  keeps the existing stored values.
- Full reference: https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-setup-form

### Unstructured File Uploads

Send PDFs, images, archives, or other binary content to the destination alongside a metadata row,
via an optional `file` parameter on `op.upsert()`/`op.update()`. Supported only for destinations
with unstructured file replication enabled, and not supported in Hybrid Deployment.

```python
from fivetran_connector_sdk import FileUpload, Operations as op

op.upsert(
    table="invoices",
    data={"id": invoice_id, "updated_at": updated_at},
    file=FileUpload(path=f"invoices/{invoice_id}.pdf", stream=response.raw, expected_bytes=size),
)
```

- `FileUpload(path, stream, expected_bytes=None)`: `path` is the destination path within the
  table's namespace (stored in the auto-created `_fivetran_file_path` column — never set that
  column manually); `stream` is any object with `read(size) -> bytes` (`io.BytesIO`, a file
  handle, `requests.raw`); `expected_bytes` optionally verifies the upload wasn't truncated.
- Fivetran uploads the file first, then the metadata row; a failed sync retries both from the
  last checkpoint.
- If the source response is compressed, decode it first — e.g. set `response.raw.decode_content
  = True` before passing `response.raw`, or the uploaded file will be corrupted.
- To update a file, call `upsert()`/`update()` again with the same primary key and a new
  `FileUpload`. To delete, use `op.delete()` on the metadata row — this does not remove the
  staged file.
- Full reference: https://fivetran.com/docs/connector-sdk/technical-reference/connector-sdk-file-uploads

### Memory Management

Each connection runs in a container with a memory limit; accumulating data in Python objects
(`lists`, `DataFrames`, `dicts`) before delivering it scales memory with dataset size. Common
causes: collecting all pages/rows before upserting, reading a full file into memory,
`cursor.fetchall()` on a large query, or caching whole API responses.

**Fix:** fetch a small chunk → process/upsert it immediately → checkpoint → repeat. Never
accumulate the full dataset before the first `op.upsert()` call.

To measure locally: `fivetran debug` reports peak memory at the end of the run. To pinpoint the
allocating line, use `tracemalloc` (built in — take snapshots before/after suspect operations,
compare with `snapshot.statistics("lineno")`) or `psutil` (`process.memory_info().rss`) for a
coarser process-level reading at key checkpoints. Remove these calls before deploying.
Full reference: https://fivetran.com/docs/connector-sdk/testing/connector-memory-management

### Proxy Agent (Private Preview)

Lets a connector reach a data source behind your firewall through an agent installed in your
network, so no inbound firewall ports need to open. Not supported with Hybrid Deployment.

- `configuration.json` must hold the source's `host:port` endpoint(s) as a **string** value —
  this repo's configuration.json contract is flat strings only, so use a single `host:port` under
  the key `host`, or multiple endpoints as one comma-separated string under the key `hosts` (e.g.
  `"hosts": "db-primary.internal.com:5432,db-replica.internal.com:5432"`) — both are
  auto-detected. A custom key name can be passed via `--proxy-host-config-key` at deploy time.
- Deploy with `fivetran deploy --proxy-id <PROXY_AGENT_ID> [--proxy-host-config-key <key>] ...`.
- `fivetran debug` does not route through the Proxy Agent — it can't validate end-to-end
  connectivity locally; a setup-form `add_test()` connectivity check only runs from the dashboard.
- Full reference: https://fivetran.com/docs/connector-sdk/building-connectors/connection-options/proxy-agent

### Custom Database Drivers (Private Preview)

If a connector needs a database driver not pre-installed in the runtime container, package the
installation steps alongside the connector:

```text
my_connector/
├── connector.py
├── configuration.json
└── drivers/
    └── installation.sh
```

Every file under `drivers/` is packaged on deploy — include only what belongs in the deployment.
Inside `installation.sh`, each `configuration.json` key is available as an env var prefixed
`configuration_` (e.g. `db_name` → `$configuration_db_name`).
Full reference: https://fivetran.com/docs/connector-sdk/building-connectors/custom-database-drivers

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
- **Table/column names are transformed for the destination** (lowercase snake_case; non-letter/digit/underscore chars become `_`; camelCase splits) — `schema()` and `op.upsert()`/`op.update()`/`op.delete()`/`op.truncate()` must use **identical** identifiers, or a spelling/case/delimiter mismatch (e.g. `forecast` vs. `forcast`, or `user_data` vs. `user-data`) silently creates a duplicate or wrongly-merged destination table with no error.

## Connector Discovery

**Where to look:** patterns & examples → `connector_sdk` (exhaustive). Community connectors → `community_connectors`.

There are **two source repositories** — always consider both before building from scratch:

| Repository | Use for | `--template` prefix |
|------------|---------|---------------------|
| **Examples** — [SDK examples](https://github.com/fivetran/connector_sdk/tree/main/examples) | Foundational connector structure and reusable patterns for auth, pagination, sync strategy, and error handling | `examples/<path>` |
| **Community connectors** — https://github.com/fivetran/community_connectors/ | Source-specific, ready-to-use connectors for real APIs and databases | `connectors/<name>` |

Before building a new connector:
1. Check the **community connectors** repo for an exact/fuzzy match for the source.
2. Identify which **examples** (common patterns) apply based on auth, pagination, and sync style — these apply to every connector regardless of source.
3. Start from the best match with `fivetran init --template <prefix>` (`connectors/<name>` resolves to `community_connectors`; `examples/<path>` resolves to `connector_sdk`; no flag uses the default `_template_connector`).

## Example discovery

Use the repositories in **Connector Discovery** above. Read their current README
or directory listing to locate relevant examples; use an existing local checkout
when available, otherwise the repository's web listing or contents API. Follow
paths you discover rather than guessing filenames or assuming an older layout.

Choose examples by the behavior needed: connector structure and configuration,
authentication, pagination, incremental cursors/checkpoints, or large-volume
processing. Community connectors can supply source-specific implementations.
Read the relevant source and accompanying documentation before adapting a pattern;
reuse examples already identified in this task. If a path is missing, return to
the current listing to resolve it instead of trying URL variations.

## Reference Documentation
- [Connector SDK Overview](https://fivetran.com/docs/connector-sdk)
- [Technical Reference](https://fivetran.com/docs/connector-sdk/technical-reference)
- [Supported Datatypes](https://fivetran.com/docs/connector-sdk/technical-reference#supporteddatatypes)
- [Best Practices](https://fivetran.com/docs/connector-sdk/best-practices)
- [SDK Repository](https://github.com/fivetran/connector_sdk)
