---
name: build-connector
description: Build a new Fivetran connector from a description. Use when the user wants to create, generate, or scaffold a new connector for an API or data source.
argument-hint: "Describe the connector (e.g., 'Stripe API connector for payments and customers')"
---

<!--
  GENERATED FILE — DO NOT EDIT.
  Canonical source: canonical/skills/build-connector/SKILL.md
  Regenerate with: bash scripts/sync-plugins.sh
-->

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

Apply the validator workflow — read `workflows/validator.md` in the plugin directory (or, in plugins that support subagents, invoke the `connector-validator` subagent) to research the API and produce a complete specification **and a discovery result**: `EXACT MATCH`, `FUZZY MATCH`, or `BUILD ON TEMPLATE`.

**Stop and wait** for the user to answer any clarifying questions the validator surfaces before proceeding to Phase 2.

## Phase 2: Scaffold the Project with `fivetran init`

`fivetran init` is the canonical scaffolding path — it produces a complete, runnable connector with the correct structure (`validate_configuration()`, docstrings, the `__main__` block). **Always scaffold with `fivetran init`; never hand-write the project from scratch.** Pick the command from the Phase 1 discovery result. The project directory is the connector name (lowercase, underscores).

- **EXACT MATCH / FUZZY MATCH** — start from the community connector:
  ```bash
  printf '\n' | fivetran init "<connector_dir>" --template connectors/<name> --force
  ```
- **BUILD ON TEMPLATE** — start from the default template:
  ```bash
  printf '\n' | fivetran init "<connector_dir>" --force
  ```

Windows PowerShell: replace `printf '\n' |` with `"" |`.

**Why the piped newline and `--force`:** `fivetran init` always runs an interactive "which coding agent shall we install the plugin for?" prompt, and there is no flag to skip it. `--force` auto-confirms project creation and file overwrites; the piped empty line answers the agent prompt with an invalid choice, so it logs `invalid choice; skipping agent setup` (this is **expected and benign** — the plugin is already installed) and continues.

**Verify success by checking that `<connector_dir>/connector.py` exists**, not by the exit code — an exhausted input pipe can make `init` exit non-zero even after the files download correctly. `connectors/<name>` resolves to the `community_connectors` repo; `examples/<path>` resolves to `fivetran_connector_sdk`.

## Phase 3: Customize the Scaffolded Files

Apply the generator workflow — read `workflows/generator.md` (or invoke the `connector-generator` subagent) to adapt the **already-scaffolded** files to the Phase 1 specification using `Edit` (do not rewrite from scratch). For an EXACT MATCH, the connector may need little or no change beyond configuration; for FUZZY/BUILD ON TEMPLATE, study 2–4 relevant SDK examples and adapt `connector.py`, `configuration.json`, and `README.md` to the spec. Preserve the template structure (`validate_configuration()`, docstrings, global `connector = Connector(...)`, the `__main__` block).

## Phase 4: Setup Environment

`fivetran init` already created `requirements.txt` (or `pyproject.toml`). Set up the virtual environment and install dependencies with commands appropriate for the user's OS:

macOS/Linux:
```bash
cd "<project_directory>"
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt fivetran_connector_sdk
```

Windows PowerShell:
```powershell
cd "<project_directory>"
uv venv .venv
uv pip install --python .\.venv\Scripts\python.exe -r requirements.txt fivetran_connector_sdk
```

## Phase 5: Enter Configuration & Test

After scaffolding and customizing the files (or finding existing files with placeholder values), credentials must be entered via the encryption script. This is **not negotiable** and **not a user choice** — it is the only supported flow.

**HARD RULES — violating any of these is a failure:**
- DO NOT use `AskUserQuestion` (or any choice-menu / multi-option UI) to ask how the user wants to enter credentials. There is exactly one way.
- DO NOT present "Paste in chat", "Edit the file yourself", "Use a public repo", or any other option as a credential-entry choice.
- DO NOT tell the user to edit `configuration.json` manually under any circumstances.
- DO NOT accept credentials pasted in chat.
- DO NOT run `enter_configuration.py` yourself. The user must run it in their own separate terminal.
- DO NOT proceed to running `run_connector.py` until credentials are encrypted (the runner will refuse plaintext config anyway).

**THE ONLY ACCEPTABLE FLOW.** Output the following message to the user as plain text (substitute `<plugin>` with the actual plugin directory path, and `<connector_dir>` with the connector directory). Use one fenced command block: `bash` on macOS/Linux, `powershell` on Windows. Quote both paths. Do not insert a line break inside the `python` command.

````text
I've generated the connector files (or the files already exist). To fill in credentials securely, open a separate terminal, then run:

```bash
cd "<connector_dir>"
python "<plugin>/tools/enter_configuration.py" "configuration.json"
```

The script will prompt you for each credential field and encrypt them in place. I never see the plaintext values. Let me know when it's done and I'll run the test.
If the local encryption secret file does not exist yet, the script creates it first.
````

After the user confirms credentials are entered, run the connector via the secure runner:

```bash
python <plugin>/tools/run_connector.py <connector_dir>
```

This decrypts the config in memory and passes it via named pipe — plaintext credentials never touch disk. If `run_connector.py` exits with "configuration.json is not encrypted", the user bypassed the encryption script; loop back to the directive above and do not retry the test until encryption is done.

Check results:

macOS/Linux:
```bash
.venv/bin/python -c "
import duckdb
conn = duckdb.connect('files/warehouse.db')
tables = conn.execute(\"SELECT table_name FROM information_schema.tables WHERE table_schema = 'tester'\").fetchall()
print(f'Tables synced: {len(tables)}')
for (t,) in tables:
    count = conn.execute(f'SELECT COUNT(*) FROM tester.{t}').fetchone()[0]
    print(f'  tester.{t}: {count} rows')"
```

Windows PowerShell:
```powershell
.\.venv\Scripts\python.exe -c 'import duckdb; conn = duckdb.connect("files/warehouse.db"); tables = conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = ''tester''").fetchall(); print("Tables synced:", len(tables)); [print("  tester." + t + ": " + str(conn.execute("SELECT COUNT(*) FROM tester." + t).fetchone()[0]) + " rows") for (t,) in tables]; conn.close()'
```

Report: tables synced, row counts, any errors.

## Phase 6: Auto-Fix on Failure

If the test fails:

1. Read the error output carefully.
2. Classify the error:
   - **INFRA error** (network, JVM, SDK internal): explain the infrastructure issue. Do NOT change code.
   - **FIRST_RUN error** (connector has never succeeded — likely credentials/config): guide the user to verify config. Do NOT change code.
   - **CODE error** (syntax, logic, SDK misuse): apply the fixer workflow — read `workflows/fixer.md` (or invoke the `connector-fixer` subagent). Re-test after fixing.
   - **TOOL error** (`run_connector.py` fails): report to the user. Do NOT modify plugin tools.

**IMPORTANT**: Never modify plugin tools. Only fix the user's connector code.
