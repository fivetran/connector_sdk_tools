# Changelog

Changes for the Fivetran AI coding agent tools in this repository.

## September 2026

### fivetran-connector-sdk-tools 2026.9.18.1

- Corrected runtime facts in sdk-reference.md against the current SDK source/CLI: production and local-debug memory limit is 4 GB (was documented as 1 GB in production), the default deploy Python version is 3.14 (was documented as 3.13), and dropped an unverified "0.5 vCPUs" claim not found in any current source.
- Broadened the `exit()` gotcha to also cover `sys.exit()` and `os._exit()` — the SDK's own static check in `connector.py` flags all three, not just bare `exit()`.
- Documented that the `Connector(...)` instance must be assigned to a module-level variable named exactly `connector` — the SDK looks for that name specifically; any other name is a SEVERE error even for an otherwise-valid object. Added as a required check in evaluate-connector.

- Documented the Connector SDK setup form (`configuration_form`, `ConfigurationForm`, `form_field.TextField|DropdownField|ToggleField`, `ConfigurationForm.add_test`/`Test`) in sdk-reference.md, closing an awareness gap inherited by every downstream skill and agent.
- connector-generator now offers to add a setup form when the connector needs credentials or dashboard-configurable settings, and only adds one with the user's agreement.
- evaluate-connector flags a missing `configuration_form()` as a good-to-have "Configurability" finding when `connector.py` reads credential- or connection-specific-looking keys from the `configuration` dict (never based on `configuration.json`'s actual contents, which the evaluator does not read).
- deploy-connector now warns that redeploying with a local `configuration.json` updates the connection's stored configuration (not just the code), so local-only values should be checked before a routine redeploy.
- build-connector now confirms the project/connector name with the user before scaffolding, instead of silently deriving it from the current path.
- test-connector adds guidance for diagnosing a slow or stuck local sync with py-spy CPU profiling.
- sdk-reference.md and the generator workflow now give concrete logging-milestone guidance (by record count, by entity/table, or by elapsed time) so long-running syncs don't go silent long enough to look hung.
- Documented `op.error()`/`op.warning()` in sdk-reference.md's operations table, including the distinction from `log.error()`/`log.warning()` (log-only, no dashboard alert) and a retry/warn-and-continue/fail-fast response table; mirrored into the generator workflow and evaluate-connector's checklist.
- Documented Unstructured File Uploads (`FileUpload`, `op.upsert(..., file=...)`), Connector Memory Management (common causes, fetch-process-checkpoint pattern, `tracemalloc`/`psutil` local measurement), Proxy Agent, and Custom Database Drivers in sdk-reference.md.
- test-connector adds guidance for diagnosing high local memory usage (`tracemalloc`/`psutil`), alongside the existing py-spy profiling guidance.
- Documented destination table/column name normalization in sdk-reference.md and the generator workflow, and added an evaluate-connector check for schema/upsert table-name mismatches that silently create duplicate or wrongly-merged destination tables.
- Added a `--no-configuration` flag to `deploy_connector.py` so a code-only redeploy can skip pushing the local `configuration.json` — it strips an inherited `FIVETRAN_CONFIGURATION` environment variable, and temporarily renames the local `configuration.json` out of the way within the same project directory for the deploy subprocess (since `fivetran deploy` auto-loads it from its working directory even without `--configuration`), restoring it afterward via a normal exit path plus an atexit/SIGTERM safety net. Kept in the same directory rather than a shared system temp path, so a same-filesystem rename never risks changing file permissions on a credential-bearing file, and so the original is trivially recoverable under an obvious name if the process is ever killed before it can restore automatically. Documented in deploy-connector as the safe way to redeploy without overwriting production configuration.

### fivetran-connector-sdk-tools 2026.9.12.1

- Centralized example discovery in sdk-reference.md to eliminate duplication across agent and workflow documentation.
- Replaced hardcoded URLs and file paths in connector-fixer, connector-generator, and connector-validator agents with topic-based guidance that defers to a single source of truth.
- Removed redundant sections from agents and workflows, streamlining maintenance and reducing outdated reference links.

## July 2026

### fivetran-connector-sdk-tools 2026.7.8.1

- Supports AI-assisted connector development in Claude Code, Codex CLI, Gemini CLI, GitHub Copilot CLI, and GitHub Copilot IDE integrations installed from source.
- Provides workflows to build, test, deploy, evaluate, fix, and migrate connectors using coding agents.
- Includes migration support for Fivetran Functions connectors, Meltano extractors or Singer taps, and Airbyte source connectors.
- Includes local tools for secure configuration entry, local connector runs, and deployment to Fivetran.
- Updated Claude Code, Codex CLI, Gemini CLI, and GitHub Copilot plugin manifests to version `2026.7.8.1`.
