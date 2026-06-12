---
name: migrate-functions-connector
description: Migrate an existing Fivetran Functions connector to a Fivetran Connector SDK connector. Use when the user has an AWS Lambda, Azure Function, Google Cloud Function, or other Fivetran Functions connector they want to port to CSDK.
---

> **Context**: This plugin is for the Fivetran Connector SDK (CSDK). "CSDK" is shorthand for "Connector SDK".

# Migrate a Fivetran Functions Connector to CSDK

**FIRST**: Read `sdk-reference.md` from the plugin directory to load SDK rules, operation names, schema constraints, configuration rules, and testing requirements.

Use this workflow to convert an existing Fivetran Functions connector into a Connector SDK project. Functions connector examples and migration references:
- Official docs: https://fivetran.com/docs/connectors/functions
- Public examples: https://github.com/fivetran/functions

When validating the migration workflow itself, use representative examples from the public repository:
- `api/aws_lambda/index.js` for JavaScript AWS Lambda with `request.secrets`, `request.state`, `insert`, `delete`, `schema`, and `hasMore`.
- `softDelete/aws-lambda.py` for Python AWS Lambda with top-level `softDelete`.
- `Azure-Function/Pyhton/azure-function.py` for Azure Function response wrapping.
- `file/csv/aws_lambda/index.js` for file parsing behavior.

## Step 1: Locate the Source and Target

If the user did not provide a source path, ask for the directory or file containing the Functions connector. Accept AWS Lambda, Azure Functions, Google Cloud Functions, or standalone handler examples.

Find or create the target CSDK project:
- If the current directory already has `connector.py`, `configuration.json`, and `requirements.txt`, migrate in place.
- If no CSDK project exists, ask for the target directory name, then scaffold it with `fivetran init` before editing files.
- Do not overwrite unrelated files.

## Step 2: Inventory the Functions Connector

Read the source code and identify:
- Runtime and platform: AWS Lambda, Azure Functions, Google Cloud Functions, or other.
- Language: Python, JavaScript/Node.js, Java, or other.
- Handler entry point and provider glue.
- Configuration inputs from `request.secrets`, environment variables, or cloud secret services.
- State inputs from `request.state`.
- Output shape: `insert`, `delete`, `softDelete`, `schema`, `state`, `hasMore`, and error handling.
- Tables, primary keys, cursor fields, pagination, and incremental sync logic.
- Dependencies and source-specific client libraries.
- Any setup/test behavior separate from sync behavior.
- Source naming quirks and bugs. Preserve table/column/state names unless renaming is clearly intentional, then document the change.

Do not ask the user to paste credentials in chat. Replace real values with placeholders if they appear in source files.

## Step 3: Map Functions Concepts to CSDK

Use this mapping:

| Functions connector concept | Connector SDK concept |
|-----------------------------|-----------------------|
| Cloud provider handler | Remove; CSDK uses `connector = Connector(update=update, schema=schema)` |
| `request.secrets` | `configuration` dict from `configuration.json` |
| `request.state` | `state` dict passed to `update(configuration, state)` |
| Returned `schema` object | `schema(configuration)` return list with `table`, `primary_key`, optional `columns` |
| `insert[table]` records | `op.upsert(table=table, data=record)` |
| `delete[table]` records | `op.delete(table=table, keys={...primary key values...})` |
| `softDelete` table list | `op.truncate(table=table)` for each listed table, checkpointed after the safe boundary |
| Returned `state` | `op.checkpoint(state=new_state)` |
| `hasMore: true` | Loop inside `update()` until the page/batch is complete, checkpointing safely |
| Callback/error response | Raise exceptions and use SDK logging |

Function connector `delete` records are full records in many examples. For CSDK `op.delete`, pass only the declared primary-key values.
Function connector `softDelete` marks all previously synced rows in a table as deleted. For CSDK, use `op.truncate(table=...)` only when the Functions connector returned that table in `softDelete`; do not replace row-level deletes with truncate.

## Step 4: Port the Implementation

Edit the CSDK project files:

### `connector.py`
- Keep the scaffolded structure where present: `validate_configuration()`, `schema()`, `update()`, global `connector = Connector(...)`, and `if __name__ == "__main__": connector.debug()`.
- Port source extraction logic into Python helper functions.
- Translate JavaScript/Java Functions code into Python behavior; do not wrap cloud-provider handlers.
- Remove AWS Lambda/Azure/GCP request/response glue.
- Replace `request.secrets` with `configuration`.
- Replace `request.state` with `state`.
- Emit rows using SDK operations directly. Do not `yield` operations.
- Call `op.checkpoint(state=state)` after each safe batch.
- Preserve incremental cursor semantics. If the Function connector used `hasMore`, implement an internal loop with clear stop conditions.
- Preserve soft-delete semantics with `op.delete()` where the Function connector populated `delete`.
- Preserve table-wide soft-delete semantics with `op.truncate()` where the Function connector populated top-level `softDelete`.
- Add retry handling for HTTP 429 and transient 5xx responses.
- Keep type hints simple: use `dict` and `list`; do not import `Dict`, `Any`, or use `op.Operation`.

### `configuration.json`
- Keep flat string key/value pairs only.
- Include fields needed by the connector, using obvious placeholders only.
- Do not include real credentials from the source Function connector.
- Do not use arrays or nested objects.

### `requirements.txt`
- Include only source-specific dependencies not already available in the CSDK environment.
- Do not include `fivetran_connector_sdk`.
- Do not include cloud provider serverless runtime packages unless the migrated connector still truly needs them.

### `README.md`
- Explain that this connector was migrated from a Fivetran Functions connector.
- Document configuration fields with placeholders only.
- Direct users to `tools/enter_configuration.py` for secure configuration entry.

## Step 5: Validate the Migration

Check behavior before testing:
- Every table from the Function connector has a CSDK schema entry with a primary key.
- Every `insert` table maps to `op.upsert`.
- Every `delete` table maps to `op.delete` using primary-key fields only.
- Every `softDelete` table maps to `op.truncate` only when the source connector used table-wide soft delete.
- Cursor/state names preserve the original incremental semantics.
- `hasMore` behavior is represented by an internal pagination loop or by checkpointed progress.
- No cloud-provider handler code is required for local CSDK execution.
- No real credentials are present in source files, README, or chat.

Then follow the secure test flow from `test-connector`:
- Run the secure runner, not `fivetran debug` directly.
- If configuration values need to be entered or refreshed, direct the user to run `tools/enter_configuration.py` in their own terminal.
- Do not inspect or print configuration values.

## Step 6: Report Results

Summarize:
- Source Function connector platform/language.
- Tables migrated and primary keys.
- State/cursor mapping.
- Any behavior that changed intentionally.
- Remaining manual checks, especially API credentials, endpoint access, and data parity against the original Function connector.
