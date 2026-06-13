---
name: migrate-airbyte-connector
description: Migrate an existing Airbyte source connector to a Fivetran Connector SDK connector. Use when the user has an Airbyte Python CDK source, low-code YAML manifest, source connector directory, configured catalog, spec/config/state files, or Airbyte protocol output they want to port to CSDK.
argument-hint: "Path or description of the Airbyte source connector to migrate"
---

> **Context**: This plugin is for the Fivetran Connector SDK (CSDK). "CSDK" is shorthand for "Connector SDK".

# Migrate an Airbyte Source Connector to CSDK

**FIRST**: Read `sdk-reference.md` from the plugin directory to load SDK rules, operation names, schema constraints, configuration rules, and testing requirements.

Use this workflow to convert Airbyte source connector logic into a Connector SDK project. Airbyte migration references:
- Airbyte protocol docs: https://docs.airbyte.com/platform/understanding-airbyte/airbyte-protocol/
- Airbyte connector specification reference: https://docs.airbyte.com/platform/connector-development/connector-specification-reference
- Airbyte Python CDK docs: https://docs.airbyte.com/platform/connector-development/cdk-python
- Airbyte low-code connector docs: https://docs.airbyte.com/platform/connector-development/config-based/low-code-cdk-overview
- Fivetran CLI for platform resources: https://pypi.org/project/fivetran-cli/

When validating the migration workflow itself, use representative public connectors such as Airbyte's `source-github`, which exercises:
- Python CDK source structure with `source.py`, stream classes, schema files, utilities, and tests.
- Nested credential objects with `oneOf` auth modes and `airbyte_secret` fields.
- Array settings such as `repositories` and `branches`, plus deprecated string aliases such as `repository` and `branch`.
- Wildcard repository expansion and config preflight validation.
- Parent-child streams, stream slices, per-stream state, semi-incremental streams, GraphQL/REST pagination, rate-limit token rotation, and stream-level failure handling.

## Step 1: Locate the Source and Target

If the user did not provide a source path, ask for one of:
- An Airbyte source connector directory, such as `source-<name>/`.
- A Python CDK source package with `source.py`, stream classes, schemas, and tests.
- A low-code connector manifest YAML file.
- Airbyte artifacts: `spec.json`, `config.json`, `catalog.json`, `configured_catalog.json`, `state.json`, and sample Airbyte protocol output.

Find or create the target CSDK project:
- If the current directory already has `connector.py`, `configuration.json`, and `requirements.txt`, migrate in place.
- If no CSDK project exists, ask for the target directory name, then scaffold it with `fivetran init` before editing files.
- Do not overwrite unrelated files.

Scope the migration:
- Migrate Airbyte sources only.
- Do not port Airbyte destinations, normalization, workspace/job orchestration, Docker packaging, or Airbyte platform metadata into `connector.py`.
- For Airbyte platform resources that correspond to Fivetran platform objects, create a follow-up plan using `fivetran-cli` instead of embedding that behavior in connector code.

## Step 2: Inventory the Airbyte Source

Read source files and identify:
- Connector type: Python CDK source, low-code YAML manifest, Java/custom source, or protocol artifacts only.
- Source entry points: `spec`, `check`, `discover`, and `read` command implementations.
- Configuration schema from `spec.json`, `connectionSpecification`, manifest `spec`, or CDK `spec()`.
- Credential fields from `airbyte_secret`, OAuth/authenticator config, environment variables, or docs.
- Config migrations and deprecated aliases, such as old root-level credentials or string fields that are normalized into newer nested/array config shapes.
- Selected streams from `configured_catalog.json`, connection catalog, low-code manifest, or user request.
- Stream schema from Airbyte catalog `json_schema`, manifest schemas, schema files, CDK stream classes, or sample `CATALOG`/`RECORD` messages.
- Primary keys from `source_defined_primary_key`, configured stream primary keys, stream class fields, or docs.
- Sync mode per stream: `incremental` or `full_refresh`.
- Destination sync mode per stream: `append`, `append_dedup`, or `overwrite`.
- Cursor field resolution from source-defined cursor, configured `cursor_field`, default cursor field, manifest cursor, or CDK stream cursor.
- State shape from `state.json`, Airbyte `STATE` messages, stream state, global state, or CDK state methods.
- Request logic: base URL, paths, request parameters/body/headers, authenticators, pagination, stream slices/partitions, record selector, transformations, retries, and error handling.
- Config preflight logic that expands wildcards, validates resource existence, or normalizes user inputs before stream construction.
- Parent-child stream dependencies. Some selected child streams require parent stream API calls for context even when the parent stream is not selected for output.
- Stream-level failure policy, including connectors that continue syncing other streams after one stream fails or is unavailable.
- Airbyte platform intent from destinations, connections, schedules, normalization, and jobs. Record this separately as potential `fivetran-cli` follow-up work.

Do not ask the user to paste credentials in chat. Do not print `config.json`, `.env`, or OAuth credentials. Replace real values with placeholders if they appear in source files.

## Step 3: Map Airbyte Concepts to CSDK

Use this mapping:

| Airbyte concept | Connector SDK concept |
|-----------------|-----------------------|
| Airbyte source connector | One CSDK connector, or one scoped connector per source if the repo contains multiple unrelated sources |
| `spec.json` / `connectionSpecification` / manifest `spec` | Flat string fields in `configuration.json` |
| `airbyte_secret: true` | Sensitive configuration field; placeholder only, entered through secure config tool |
| Airbyte array/object config fields | Prefer separate connector deployments for multi-entity sync; use JSON-encoded string fields parsed with `json.loads()` only when unavoidable for source-connector parity |
| Airbyte config migrations / deprecated aliases | Backward-compatible parsing or documented renamed fields |
| `check` command | `validate_configuration(configuration)` or a lightweight authenticated probe |
| `discover` output / Airbyte catalog stream | CSDK `schema(configuration)` table entry |
| Airbyte JSON Schema properties | Optional CSDK `columns` with SDK data types |
| Configured/selected streams | Tables and fields implemented by `schema()` and `update()` |
| Parent streams used only for context | Internal helper/API calls; do not emit the parent table unless selected |
| Airbyte `RECORD` message data | `op.upsert(table=stream, data=record)` |
| Airbyte `STATE` message | `op.checkpoint(state=new_state)` |
| Airbyte `LOG` and `TRACE` messages | SDK logging and exceptions; do not emit as rows |
| Airbyte per-stream tolerated errors | Catch/log documented nonfatal stream errors and continue only when the source connector did so |
| `incremental` sync mode | Cursor logic inside `update(configuration, state)` |
| `full_refresh` sync mode | Snapshot logic with explicit truncate/upsert decision |
| Destination sync mode `overwrite` | `op.truncate(table=...)` only when full snapshot replacement is intended |
| Destination sync mode `append_dedup` | `op.upsert(...)` with declared primary key |
| Destination sync mode `append` | Requires explicit primary-key strategy before CSDK migration |

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

Airbyte append-only streams need explicit review. CSDK tables should have stable primary keys. If an Airbyte stream has no primary key because the old destination used append mode, ask the user for a stable key strategy or document a generated deterministic key based on immutable source fields. Do not invent a lossy key silently.

Deletion behavior needs explicit review. If the Airbyte source emits deletion markers or CDC fields, map confirmed row deletes to `op.delete(table=..., keys={...})` using primary-key fields only. Do not infer deletes from missing records unless the stream is explicitly full-refresh overwrite and the migration intentionally uses `op.truncate`.

## Step 4: Port the Implementation

Edit the CSDK project files:

### `connector.py`
- Keep the scaffolded structure where present: `validate_configuration()`, `schema()`, `update()`, global `connector = Connector(...)`, and `if __name__ == "__main__": connector.debug()`.
- Port extraction logic directly into Python helper functions.
- For Python CDK sources, reuse small pure request/parse helpers where practical, but remove Airbyte command dispatch, Docker assumptions, protocol message generation, and CDK runtime dependencies.
- For low-code YAML manifests, translate manifest components into Python: requester/authenticator, pagination, record selector, stream slices, transformations, and cursor logic.
- If only Airbyte artifacts exist and no source code is available, treat catalog/spec/sample output as a behavior specification and reimplement from the source API/database/file protocol.
- Replace Airbyte config access with `configuration`.
- Replace Airbyte state with the CSDK `state` dict. Preserve the original state shape when it makes parity easier.
- Emit rows using SDK operations directly. Do not `yield` operations and do not print Airbyte JSON messages.
- Call `op.checkpoint(state=state)` after each safe page, slice, batch, or stream boundary.
- Preserve configured stream selection; do not silently add streams that were disabled in Airbyte.
- Preserve incremental cursor semantics, including start-date behavior for empty state.
- Preserve preflight normalization and validation that affects stream construction, such as wildcard expansion, deprecated config aliases, repository/org discovery, and branch normalization.
- Preserve documented stream-level failure behavior. If the Airbyte connector continued after a stream-specific 403/404/409/422/5xx, implement the same scoped skip/log behavior; otherwise raise.
- Add retry handling for HTTP 429 and transient 5xx responses.
- Keep type hints simple: use `dict` and `list`; do not import `Dict`, `Any`, or use `op.Operation`.

### `configuration.json`
- Keep flat string key/value pairs only.
- Include fields needed by the connector, using obvious placeholders only.
- Convert nested Airbyte settings to clear flat names, and document any rename.
- Prefer separate connector deployments for multi-entity configs (see `sdk-reference.md`). Only when the source connector truly requires multi-item selection, represent Airbyte arrays or objects as JSON-encoded string placeholders, such as `"streams": "[\"users\"]"` or `"credentials": "{\"auth_type\":\"token\"}"`, then parse and validate them with `json.loads()` in `connector.py`.
- Preserve support for deprecated Airbyte config aliases when source code has explicit migration logic, or document that the CSDK connector only supports the new field names.
- Do not include real credentials from `config.json`, `.env`, or Airbyte UI exports.
- Do not use arrays or nested objects.

### `requirements.txt`
- Include only source-specific dependencies not already available in the CSDK environment.
- Do not include Airbyte CDK, Airbyte platform packages, Docker tooling, destination packages, or `fivetran_connector_sdk`.
- Do not include normalization, dbt, orchestration, or test-only dependencies.

### `README.md`
- Explain that this connector was migrated from an Airbyte source connector.
- Document source connector name, selected streams, primary keys, cursor fields, and sync modes.
- Document configuration fields with placeholders only.
- Document any behavior changes, especially append-only primary-key strategy, full-refresh overwrite/truncate behavior, delete/CDC handling, stream selection changes, and removed Airbyte platform behavior.
- Document any platform resources that were intentionally left out of connector code and should be handled with `fivetran-cli`, such as destination/connection setup, scheduling, or transformation resources.
- Direct users to `tools/enter_configuration.py` for secure configuration entry.

### `fivetran-cli` follow-up notes
- If the Airbyte deployment includes destination or connection configuration that maps to Fivetran destinations or connections, document the intended Fivetran CLI resource commands to run after connector migration.
- If the Airbyte deployment includes schedules or transformation resources that map to Fivetran platform resources, document the intended Fivetran CLI follow-up.
- Do not execute account-changing `fivetran-cli` commands unless the user explicitly asks for deployment/setup and provides the required non-secret identifiers. Never ask the user to paste API keys in chat.

## Step 5: Validate the Migration

Check behavior before testing:
- Every selected stream has a CSDK schema entry and an explicit primary-key strategy.
- Disabled streams are not emitted as tables. If a disabled parent stream is needed for child context, it is used only as an internal helper path.
- Every Airbyte `RECORD` stream maps to `op.upsert`.
- Every incremental stream checkpoints after a safe cursor boundary.
- Airbyte `STATE` shape is preserved or deliberately mapped and documented.
- Array/object configuration fields are documented as JSON-encoded strings and parsed safely.
- Deprecated config aliases and migration behavior are either supported or explicitly documented as changed.
- Preflight expansion/validation behavior that affects stream construction is preserved.
- Stream-level failure behavior matches the source connector's documented behavior.
- Full-refresh/overwrite streams have an explicit documented decision: upsert-only snapshot or `op.truncate` plus reload.
- Delete/CDC behavior is either implemented with `op.delete` using primary-key fields or explicitly documented as not present in the source connector.
- JSON Schema to CSDK column type mapping is conservative and does not invent unsupported SDK types.
- No Airbyte protocol stdout message generation remains.
- No Airbyte destination, normalization, Docker, schedule, or workspace code is required for local CSDK execution.
- Any Airbyte platform resources that should survive migration are listed as `fivetran-cli` follow-up work instead of being embedded in connector code.
- No real credentials are present in source files, README, or chat.

Then follow the secure test flow from `test-connector`:
- Run the secure runner, not `fivetran debug` directly.
- If configuration values need to be entered or refreshed, direct the user to run `tools/enter_configuration.py` in their own terminal.
- Do not inspect or print configuration values.

## Step 6: Report Results

Summarize:
- Source Airbyte connector migrated.
- Connector type: Python CDK, low-code YAML, custom, or protocol-artifact migration.
- Streams migrated, primary keys, sync modes, and cursor fields.
- Configuration fields created or renamed.
- State mapping.
- Append/full-refresh/delete behavior decisions.
- Airbyte pieces intentionally not migrated into connector code, such as destinations, normalization, Docker, schedules, and workspace metadata.
- `fivetran-cli` follow-up plan for platform resources, if applicable.
- Remaining manual checks, especially API credentials, endpoint access, rate-limit behavior, and data parity against the original Airbyte sync.
