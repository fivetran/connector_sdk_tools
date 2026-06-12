---
name: migrate-meltano-connector
description: Migrate an existing Meltano extractor or Singer tap workflow to a Fivetran Connector SDK connector. Use when the user has a Meltano project, meltano.yml extractor, custom Singer tap, catalog/state/config files, or tap source code they want to port to CSDK.
---

> **Context**: This plugin is for the Fivetran Connector SDK (CSDK). "CSDK" is shorthand for "Connector SDK".

# Migrate a Meltano Extractor or Singer Tap to CSDK

**FIRST**: Read `sdk-reference.md` from the plugin directory to load SDK rules, operation names, schema constraints, configuration rules, and testing requirements.

Use this workflow to convert Meltano extractor logic into a Connector SDK project. Meltano migration references:
- Meltano project/config docs: https://docs.meltano.com/concepts/project/
- Meltano plugin docs: https://docs.meltano.com/concepts/plugins/
- Singer spec reference: https://hub.meltano.com/singer/spec/
- Meltano Singer SDK docs: https://sdk.meltano.com/
- Fivetran CLI for pipeline resources: https://pypi.org/project/fivetran-cli/

When validating the migration workflow itself, use representative public projects such as `Matatika/example-github-analytics`, which exercises:
- A Meltano project with `tap-github`, `target-postgres`, dbt transforms, a utility plugin, a job, and a schedule.
- Selector rules like `*!.*` followed by explicitly selected streams.
- Array settings such as `repositories`.
- A third-party Singer SDK tap whose source code must be consulted for schemas, primary keys, parent-child stream context, pagination, and state behavior.

## Step 1: Locate the Source and Target

If the user did not provide a source path, ask for one of:
- A Meltano project directory containing `meltano.yml`.
- A custom Singer tap package or local tap source directory.
- Singer artifacts: `config.json`, `catalog.json` or `properties.json`, `state.json`, and sample output.

Find or create the target CSDK project:
- If the current directory already has `connector.py`, `configuration.json`, and `requirements.txt`, migrate in place.
- If no CSDK project exists, ask for the target directory name, then scaffold it with `fivetran init` before editing files.
- Do not overwrite unrelated files.

Scope the migration:
- Migrate Meltano extractors/Singer taps only.
- Do not port Meltano loaders/targets, dbt transforms, schedules, orchestration, or environments into CSDK connector code.
- For pipeline resources that correspond to Fivetran platform objects, create a follow-up plan using `fivetran-cli` instead of embedding that behavior in `connector.py`.
- Use loaders, transforms, schedules, and environments as context for what the extractor produced, how it was configured, and which Fivetran CLI resources may need to be created or updated.

## Step 2: Inventory the Meltano Source

Read source files and identify:
- Meltano project files: `meltano.yml`, lock files under `plugins/`, `.env` templates, catalog files, state files, and any local tap source.
- Extractor name, namespace, executable, variant, `pip_url`, capabilities, and settings.
- Whether the tap is a local/custom tap, a third-party package, or a MeltanoHub discoverable extractor.
- Selected streams and fields from `select`, catalog metadata, or catalog `selected` flags.
- Selection rule semantics and precedence. For example, `*!.*` followed by `issues.*` means start with all streams deselected, then include the named streams.
- Stream schema from discovery/catalog JSON, tap source classes, or sample Singer `SCHEMA` messages.
- Primary keys from `key_properties`, `table-key-properties`, SDK stream `primary_keys`, or source code.
- Replication method and replication keys from metadata, SDK stream settings, or tap source code.
- State/bookmark shape from `state.json`, Singer `STATE` messages, or tap source code.
- Tap configuration fields, defaults, env aliases, and which fields are credentials.
- Complex settings such as arrays and objects. Record how they will be represented as flat CSDK string configuration fields.
- API/database/file access logic, pagination, rate limiting, retries, and error handling.
- Parent-child stream dependencies. Some selected child streams require parent stream API calls for context even when the parent stream is not selected for output.
- Pipeline intent from loaders, targets, transformations, schedules, and environments. Record this separately from extractor migration as potential `fivetran-cli` follow-up work.

Do not ask the user to paste credentials in chat. Do not print `.env`, `config.json`, or Meltano config values. Replace real values with placeholders if they appear in source files.

## Step 3: Map Meltano/Singer Concepts to CSDK

Use this mapping:

| Meltano/Singer concept | Connector SDK concept |
|------------------------|-----------------------|
| Meltano extractor / Singer tap | One CSDK connector, or one scoped connector per source if the project has multiple unrelated extractors |
| `meltano.yml` extractor settings / tap `config.json` | Flat string fields in `configuration.json` |
| Meltano array/object settings | JSON-encoded string fields parsed with `json.loads()` in connector code |
| Meltano environment variables and setting aliases | Documented configuration fields; do not embed environment loading into connector code |
| Singer catalog stream | CSDK `schema(configuration)` table entry |
| Singer `key_properties`, `table-key-properties`, or stream `primary_keys` | CSDK `primary_key` |
| Singer JSON Schema properties | Optional CSDK `columns` with SDK data types |
| Selected streams/fields | Tables and fields implemented by `schema()` and `update()` |
| Parent streams used only for context | Internal helper/API calls; do not emit the parent table unless it was selected |
| Singer `RECORD` message | `op.upsert(table=stream, data=record)` |
| Singer `STATE.value` / bookmarks | `op.checkpoint(state=new_state)` |
| Singer incremental replication key | Cursor logic inside `update(configuration, state)` |
| Singer discovery mode | Static or configuration-aware `schema(configuration)` |

Map JSON Schema types conservatively:

| JSON Schema | CSDK column type |
|-------------|------------------|
| `boolean` | `BOOLEAN` |
| `integer` | `LONG` |
| `number` | `DOUBLE` |
| `string` with `format: date-time` | `UTC_DATETIME` |
| `string` with `format: date` | `NAIVE_DATE` |
| `string` | `STRING` |
| `object` or `array` | `JSON` |
| multiple types including `null` | Use the non-null type |
| unknown or mixed type | Omit the column type or use `JSON` when the field is structured |

Full-table behavior needs explicit review. Singer taps commonly emit current rows without an explicit delete stream. If the old Meltano pipeline relied on a target to replace/truncate data for full-table streams, document that behavior and only use `op.truncate(table=...)` when the intended CSDK behavior is to mark missing prior rows as deleted before reloading a complete snapshot.

## Step 4: Port the Implementation

Edit the CSDK project files:

### `connector.py`
- Keep the scaffolded structure where present: `validate_configuration()`, `schema()`, `update()`, global `connector = Connector(...)`, and `if __name__ == "__main__": connector.debug()`.
- Port extraction logic directly into Python helper functions.
- If the source tap is already Python, reuse small pure extraction helpers where practical, but remove Singer CLI, stdout message emission, and Meltano runtime assumptions.
- If only a Meltano plugin declaration exists and no tap source is available, treat it as a behavior/configuration specification and reimplement from the source API/database/file protocol.
- Replace tap config access with `configuration`.
- Replace Singer state/bookmarks with the CSDK `state` dict. Preserve the original bookmark shape when it makes parity easier.
- Emit rows using SDK operations directly. Do not `yield` operations and do not print Singer JSON messages.
- Call `op.checkpoint(state=state)` after each safe page, batch, or stream boundary.
- Preserve selected stream behavior; do not silently add streams that were disabled in Meltano.
- Preserve incremental cursor semantics, including start-date behavior for empty state.
- Add retry handling for HTTP 429 and transient 5xx responses.
- Keep type hints simple: use `dict` and `list`; do not import `Dict`, `Any`, or use `op.Operation`.

### `configuration.json`
- Keep flat string key/value pairs only.
- Include fields needed by the connector, using obvious placeholders only.
- Convert nested Meltano settings to clear flat names, and document any rename.
- Convert Meltano arrays or objects to JSON-encoded string placeholders, such as `"repositories": "[\"owner/repo\"]"` or `"searches": "[{\"name\":\"example\",\"query\":\"repo:owner/repo\"}]"`, then parse and validate them in `connector.py`.
- Do not include real credentials from `.env`, `config.json`, or Meltano config.
- Do not use arrays or nested objects.

### `requirements.txt`
- Include only source-specific dependencies not already available in the CSDK environment.
- Do not include Meltano, Singer SDK, Singer target packages, or `fivetran_connector_sdk`.
- Do not include loader/target/dbt/orchestrator dependencies.

### `README.md`
- Explain that this connector was migrated from a Meltano extractor/Singer tap.
- Document source extractor name, selected streams, primary keys, and cursor fields.
- Document configuration fields with placeholders only.
- Document any behavior changes, especially full-table replacement/truncate semantics, stream selection changes, and removed Meltano loader/transform/orchestration behavior.
- Document any pipeline resources that were intentionally left out of connector code and should be handled with `fivetran-cli`, such as destination/connection setup, transformations, or transformation projects.
- Direct users to `tools/enter_configuration.py` for secure configuration entry.

### `fivetran-cli` follow-up notes
- If the Meltano pipeline includes loader/target configuration that maps to Fivetran destinations or connections, document the intended Fivetran CLI resource commands to run after connector migration.
- If the Meltano pipeline includes dbt transformations or transformation projects, document the intended Fivetran CLI transformation or transformation-project commands to run after connector migration.
- Do not execute account-changing `fivetran-cli` commands unless the user explicitly asks for deployment/setup and provides the required non-secret identifiers. Never ask the user to paste API keys in chat.

## Step 5: Validate the Migration

Check behavior before testing:
- Every selected stream has a CSDK schema entry with a primary key.
- Disabled streams are not emitted as tables. If a disabled parent stream is needed for child context, it is used only as an internal helper path.
- Every Singer `RECORD` stream maps to `op.upsert`.
- Every incremental stream checkpoints after a safe cursor boundary.
- Array/object configuration fields are documented as JSON-encoded strings and parsed safely.
- Full-table streams have an explicit documented decision: upsert-only snapshot or `op.truncate` plus reload.
- JSON Schema to CSDK column type mapping is conservative and does not invent unsupported SDK types.
- No Singer stdout message generation remains.
- No Meltano loader, target, dbt, schedule, or environment code is required for local CSDK execution.
- Any Meltano pipeline resources that should survive migration are listed as `fivetran-cli` follow-up work instead of being embedded in connector code.
- No real credentials are present in source files, README, or chat.

Then follow the secure test flow from `test-connector`:
- Run the secure runner, not `fivetran debug` directly.
- If configuration values need to be entered or refreshed, direct the user to run `tools/enter_configuration.py` in their own terminal.
- Do not inspect or print configuration values.

## Step 6: Report Results

Summarize:
- Source Meltano project or tap package migrated.
- Streams migrated, primary keys, and cursor fields.
- Configuration fields created or renamed.
- State/bookmark mapping.
- Full-table replacement/truncate decision.
- Meltano pieces intentionally not migrated into connector code, such as loaders, transforms, schedules, and environments.
- `fivetran-cli` follow-up plan for pipeline resources, if applicable.
- Remaining manual checks, especially API credentials, endpoint access, and data parity against the original Meltano run.
