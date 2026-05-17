---
name: build-connector
description: Build a new Fivetran connector from a description. Use when the user wants to create, generate, or scaffold a new connector for an API or data source.
argument-hint: "Describe the connector (e.g., 'Stripe API connector for payments and customers')"
---

> **Context**: This plugin is for the Fivetran Connector SDK (CSDK). "CSDK" is shorthand for "Connector SDK".

# Build a New Fivetran Connector

**FIRST**: Read `sdk-reference.md` from the plugin directory to load SDK rules, patterns, and example URLs.

You are building a complete Fivetran connector from the user's description. This skill orchestrates the build; detailed per-phase logic lives in the plugin's workflow files.

## Phase 0: Determine the Best Build Approach

**Before doing any API research or code generation**, check whether a simpler path exists. A custom CSDK connector means the user writes and maintains code; other paths may let Fivetran manage the connector for them. Always surface better options to the user before building custom.

Run all three checks in order and present findings to the user. The user decides — if they prefer to build custom even when a managed option exists, proceed to Phase 1.

### Check 1: Is there already a native Fivetran connector for this source?

Read the bundled catalog file `native-connectors.md` in the plugin directory. Do a case-insensitive fuzzy match on the source name the user mentioned against the entries.

- **If you find a match or a very close match**, tell the user:

  > *"Fivetran already has a native **{Match}** connector ([catalog](https://fivetran.com/integrations)). That's typically the best choice — Fivetran maintains it, handles API/schema changes, and you don't write or maintain any code. You can configure it in the Fivetran dashboard. Would you like to go that route? Or do you have a specific need (e.g., custom endpoint, unsupported object, non-standard auth) that requires a custom CSDK connector?"*

  Wait for the user's answer. If they choose the native connector, stop and direct them to the Fivetran dashboard. If they want custom CSDK anyway, usually skip Check 2 and go straight to Phase 1 (Lite rarely beats an existing native).

- **If there's no match**, do NOT assert "no native connector exists." The bundled list may be out of date. Say:

  > *"I don't see **{Source}** in the bundled Fivetran catalog list, but the list may be stale. Please quickly check https://fivetran.com/integrations to confirm. If it exists there, use the native connector. If not, I'll continue to Check 2."*

  Only proceed to Check 2 after the user confirms there's no native connector.

### Check 2: Is this a good fit for a Lite Connector (AI builder)?

Lite Connectors are built with Fivetran's AI builder and **managed by Fivetran** — the customer doesn't write or maintain any code. Docs: https://fivetran.com/docs/connectors/applications/lite-connectors

Criteria for recommending Lite:
- Source is a **SaaS application** (not a database, file system, event stream, or in-house system)
- Exposes a **REST API** with **JSON responses**
- Uses **standard authentication** (API key, Bearer token, or OAuth 2)
- No complex stateful logic or heavy transformations needed

If the user's source fits these criteria, tell them:

> *"Based on what you described, **{Source}** looks like a good fit for a Fivetran [Lite Connector](https://fivetran.com/docs/connectors/applications/lite-connectors). Lite Connectors are built with Fivetran's AI builder and are **managed by Fivetran** — you won't have to write or maintain any connector code. Fivetran handles API changes, bug fixes, and upgrades. Want to try the Lite path first? It's typically faster to set up and lower ongoing maintenance than a custom CSDK connector."*

Wait for the user's answer. If they choose the Lite path, stop and direct them to the Lite Connector builder. If they want custom CSDK, continue to Phase 1.

### Check 3: Proceed with custom CSDK

If neither Check 1 nor Check 2 produced a better option, or the user explicitly chose custom CSDK, continue to Phase 1.

## Phase 1: Research & Validate Requirements

Apply the validator workflow — read `workflows/validator.md` in the plugin directory (or, in plugins that support subagents, invoke the `connector-validator` subagent) to research the API and produce a complete specification.

**Stop and wait** for the user to answer any clarifying questions the validator surfaces before proceeding to Phase 2.

## Phase 2: Generate Connector Files

Apply the generator workflow — read `workflows/generator.md` (or invoke the `connector-generator` subagent) to study 2–4 relevant SDK examples and produce `connector.py`, `configuration.json`, and `README.md`.

Create the project directory before calling the workflow; name it after the connector (lowercase, underscores).

## Phase 3: Setup Environment

```bash
cd <project_directory>
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt fivetran_connector_sdk
```

## Phase 4: Enter Configuration & Test

After generating the files, `configuration.json` contains placeholder values. To fill it in with real credentials:

**DO NOT:**
- Tell the user to edit `configuration.json` manually
- Tell the user to "paste your API key here" or similar
- Suggest any tool, editor, or method other than the encryption script below

**DO this — tell the user verbatim** (replace `<plugin>` with the actual plugin directory path):

> *"Open a separate terminal, `cd` into the connector directory, and run:*
> *`python <plugin>/tools/enter_configuration.py configuration.json`*
> *It will prompt you for each credential field and write them into `configuration.json` in encrypted form. I never see the plaintext values. Let me know when it's done."*

The `enter_configuration.py` script is the **only** correct way to populate credentials. It encrypts them at rest using a master secret stored in the user's shell environment.

After the user confirms credentials are entered, run the connector via the secure runner:

```bash
python <plugin>/tools/run_connector.py <project_directory>
```

This decrypts the config in memory and passes it via named pipe — plaintext credentials never touch disk.

Check results:

```bash
source .venv/bin/activate
python -c "
import duckdb
conn = duckdb.connect('files/warehouse.db')
tables = conn.execute(\"SELECT table_name FROM information_schema.tables WHERE table_schema = 'tester'\").fetchall()
print(f'Tables synced: {len(tables)}')
for (t,) in tables:
    count = conn.execute(f'SELECT COUNT(*) FROM tester.{t}').fetchone()[0]
    print(f'  tester.{t}: {count} rows')"
```

Report: tables synced, row counts, any errors.

## Phase 5: Auto-Fix on Failure

If the test fails:

1. Read the error output carefully.
2. Classify the error:
   - **INFRA error** (network, JVM, SDK internal): explain the infrastructure issue. Do NOT change code.
   - **FIRST_RUN error** (connector has never succeeded — likely credentials/config): guide the user to verify config. Do NOT change code.
   - **CODE error** (syntax, logic, SDK misuse): apply the fixer workflow — read `workflows/fixer.md` (or invoke the `connector-fixer` subagent). Re-test after fixing.
   - **TOOL error** (`run_connector.py` fails): report to the user. Do NOT modify plugin tools.

**IMPORTANT**: Never modify plugin tools. Only fix the user's connector code.
