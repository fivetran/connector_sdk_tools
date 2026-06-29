AI-assisted tools for building, testing, and deploying [Fivetran Connector SDK](https://fivetran.com/docs/connector-sdk) connectors. Distributed as a native plugin/extension for Claude Code, Codex CLI, Gemini CLI and GitHub Copilot CLI.

## Prerequisites

- **Python 3.10–3.14**
- **A supported coding agent** (Claude Code, Codex CLI, Gemini CLI, or GitHub Copilot CLI — see install matrix below)
- **Fivetran Connector SDK** — `pip install fivetran-connector-sdk`

## Quick Start

The fastest path: install the SDK and let `fivetran init` set everything up.

```bash
pip install fivetran-connector-sdk
fivetran init
```

`fivetran init` scaffolds a new connector project and offers to configure a coding agent for you — detecting which of Claude Code, Codex CLI, Gemini CLI, or the standalone GitHub Copilot CLI you have installed and running the relevant plugin install command on your behalf. You can also skip the agent setup if you'd rather install it yourself; see the matrix below.

## Install the plugin manually

If you skipped agent setup in `fivetran init`, or want to install the plugin into an existing project, pick your agent below. Each install uses the agent's own native install/update/uninstall — this repo does not own the lifecycle.

### Claude Code

```bash
claude plugin marketplace add fivetran/connector_sdk_tools
claude plugin install fivetran-connector-sdk@fivetran-connector-sdk-ai
```

Or from inside a Claude Code session:

```
/plugin marketplace add fivetran/connector_sdk_tools
/plugin install fivetran-connector-sdk@fivetran-connector-sdk-ai
```

See [`claude-code/README.md`](claude-code/README.md) for the full tutorial.

### Codex CLI

```bash
codex plugin marketplace add fivetran/connector_sdk_tools
codex plugin add fivetran-connector-sdk@fivetran-connector-sdk-ai
```

Plugins must also be enabled in `~/.codex/config.toml`. See [`codex/README.md`](codex/README.md) for the full setup.

Note: If your current version of Codex CLI does not support the `add` command, please upgrade to the latest version of Codex CLI.

### Gemini CLI

```bash
gemini extensions install https://github.com/fivetran/connector_sdk_tools
```

For non-interactive use (e.g., scripts):

```bash
gemini extensions install https://github.com/fivetran/connector_sdk_tools --consent --skip-settings
```

### GitHub Copilot CLI

```bash
copilot plugin marketplace add fivetran/connector_sdk_tools
copilot plugin install fivetran-connector-sdk@fivetran-connector-sdk-ai
```

See [`copilot/README.md`](copilot/README.md) for the full tutorial.

### GitHub Copilot in IDEs

The plugin assets for GitHub Copilot are included in this repository under [`copilot/`](copilot/), and the plugin can be installed directly from source. However, installing it through the Connector SDK PyPI package or `fivetran init` is **not supported** for IDE-integrated Copilot extensions (VS Code, JetBrains, etc.) as those environments manage plugin installation from within the IDE itself.

To install from source in VS Code, follow the [VS Code agent plugin install guide](https://code.visualstudio.com/docs/agent-customization/agent-plugins#_install-a-plugin-from-source) and point it at this repository. For other IDEs, consult their documentation on installing Copilot agent plugins.

## Usage

Once installed, in your connector project directory:

| Command (Claude Code / Gemini CLI / Copilot CLI) | Codex CLI | Purpose |
|---|---|---|
| `/fivetran-connector-sdk:build-connector` | `$build_connector` | Research an API and generate a new connector |
| `/fivetran-connector-sdk:test-connector` | `$test_connector` | Run and validate an existing connector locally |
| `/fivetran-connector-sdk:deploy-connector` | `$deploy_connector` | Deploy a connector to your Fivetran account |
| `/fivetran-connector-sdk:evaluate-connector` | `$evaluate_connector` | Code review and quality report |
| `/fivetran-connector-sdk:migrate-functions-connector` | `$migrate_functions_connector` | Migrate a Fivetran Functions connector to Connector SDK |
| `/fivetran-connector-sdk:migrate-meltano-connector` | `$migrate_meltano_connector` | Migrate a Meltano extractor or Singer tap to Connector SDK |
| `/fivetran-connector-sdk:migrate-airbyte-connector` | `$migrate_airbyte_connector` | Migrate an Airbyte source connector to Connector SDK |

For code fixes or modifications, describe the problem in natural language — the agent routes to the `connector-fixer` subagent automatically.

## Migration Skills

The plugin includes AI-guided migration skills for moving existing custom connector code to Fivetran Connector SDK. These are not deterministic one-shot conversion scripts; the agent reads the source connector, identifies the source runtime and data contract, ports the logic into a CSDK project, and validates the result against SDK patterns.

To use a migrator, open your coding agent in the directory where you want the migrated Connector SDK project to be created, then invoke the relevant slash command or Codex skill and point it at the existing connector source. Provide any useful local paths, example config files, catalogs, state files, schemas, tests, or docs. The agent should inspect the source first, explain the migration plan and any behavior decisions it needs, then create or update the CSDK files and run local validation where possible.

Keep real credentials out of the prompt. Use redacted example configs, placeholders, or local files that are already handled by your normal credential workflow. Migration skills may need to preserve behavior that depends on existing configuration shape, selected streams, primary keys, cursor fields, full-refresh behavior, delete semantics, or platform pipeline setup, so include those artifacts when they exist.

After migration, review the generated connector code and README, fill in local configuration values, run the plugin's test connector command, and compare the output against the old connector using a small known-good source account or fixture.

### Functions Connector Migrator

Use `/fivetran-connector-sdk:migrate-functions-connector` or `$migrate_functions_connector` to port a Fivetran Functions connector to Connector SDK.

The Functions migrator supports AWS Lambda, Azure Functions, Google Cloud Functions, and standalone handler examples. It maps Function connector concepts to CSDK concepts:

| Functions connector | Connector SDK |
|---|---|
| `request.secrets` | `configuration` |
| `request.state` | `state` |
| returned `schema` | `schema(configuration)` |
| `insert[table]` | `op.upsert(...)` |
| `delete[table]` | `op.delete(...)` with primary-key fields only |
| top-level `softDelete` | `op.truncate(...)` for listed tables |
| returned `state` | `op.checkpoint(...)` |
| `hasMore` | internal loop/checkpoint logic in `update()` |

The migrator removes cloud-provider request/response wrappers, preserves table/state naming unless a rename is intentional, and documents any behavior changes in the migrated connector README.

### Meltano Connector Migrator

Use `/fivetran-connector-sdk:migrate-meltano-connector` or `$migrate_meltano_connector` to port a Meltano extractor or Singer tap workflow to Connector SDK.

The Meltano migrator focuses on extractors/Singer taps. Meltano loaders, targets, dbt transforms, schedules, and environments are not ported into connector code; when those pipeline pieces map to Fivetran platform resources, the migrator documents them as follow-up work for `fivetran-cli`. It maps Meltano and Singer concepts to CSDK concepts:

| Meltano / Singer | Connector SDK |
|---|---|
| `meltano.yml` extractor settings / tap `config.json` | `configuration.json` |
| Singer catalog streams | `schema(configuration)` table entries |
| `key_properties` / `table-key-properties` | `primary_key` |
| Singer JSON Schema properties | optional CSDK `columns` |
| Singer `RECORD` messages | `op.upsert(...)` |
| Singer `STATE` messages / bookmarks | `op.checkpoint(...)` |
| replication key metadata | cursor logic in `update()` |

The migrator also requires an explicit decision for full-table streams: keep upsert-only snapshot behavior, or use `op.truncate(...)` before reloading a complete snapshot when the old pipeline relied on replacement semantics. For pipeline setup beyond connector code, install and use `fivetran-cli` (`python3 -m pip install -U fivetran-cli`) after the CSDK connector migration.

### Airbyte Connector Migrator

Use `/fivetran-connector-sdk:migrate-airbyte-connector` or `$migrate_airbyte_connector` to port an Airbyte source connector to Connector SDK.

The Airbyte migrator focuses on source connectors. Airbyte destinations, normalization, workspace/job orchestration, Docker packaging, schedules, and platform metadata are not ported into connector code; when those pieces map to Fivetran platform resources, the migrator documents them as follow-up work for `fivetran-cli`. It maps Airbyte concepts to CSDK concepts:

| Airbyte | Connector SDK |
|---|---|
| `spec.json` / `connectionSpecification` | `configuration.json` |
| `airbyte_secret` fields | sensitive config placeholders entered securely |
| Airbyte catalog streams | `schema(configuration)` table entries |
| JSON Schema properties | optional CSDK `columns` |
| configured streams | tables implemented by `schema()` and `update()` |
| `RECORD` messages | `op.upsert(...)` |
| `STATE` messages | `op.checkpoint(...)` |
| incremental sync mode | cursor logic in `update()` |
| full-refresh overwrite | explicit `op.truncate(...)` plus reload decision |

The migrator also requires explicit decisions for append-only streams without primary keys, full-refresh overwrite behavior, and delete/CDC markers. It does not infer deletes from missing records unless the source stream is intentionally migrated as full-refresh overwrite.

## Temporary Configuration Tool Dependency

Until secure configuration entry is available directly in the Fivetran Connector SDK CLI, the plugin uses `tools/enter_configuration.py` to encrypt `configuration.json`. Before running that script, install the plugin tool dependencies in the same terminal:

```bash
python -m pip install -r "/path/to/plugin/tools/requirements.txt"
```

For Claude Code installed from the marketplace, the path will look like:

macOS/Linux:
```bash
python -m pip install -r "$HOME/.claude/plugins/cache/fivetran-connector-sdk-ai/fivetran-connector-sdk/<version>/tools/requirements.txt"
```

Windows PowerShell:
```powershell
python -m pip install -r "$env:USERPROFILE\.claude\plugins\cache\fivetran-connector-sdk-ai\fivetran-connector-sdk\<version>\tools\requirements.txt"
```

On first run, `enter_configuration.py` creates a local encryption secret under your user profile:

- macOS/Linux: `~/.fivetran/csdk_master_secret`
- Windows: `%USERPROFILE%\.fivetran\csdk_master_secret`

It uses that secret to encrypt every configuration field value. Those encrypted values are written inline in `configuration.json` with an `ENCRYPTED:v1:<key_id>:local-fernet:` prefix. The AI does not see plaintext configuration values. To start configuration entry over, run `enter_configuration.py` again.

Only `enter_configuration.py` creates the secret. The test and deploy tools require the existing secret to decrypt configuration values at runtime.

## Security Model

The configuration encryption in this plugin is **local-at-rest protection** for AI-assisted development. Its primary purpose is to keep sensitive configuration values out of the AI conversation and out of local files that agents may need to reason around.

`enter_configuration.py` runs in the user's own terminal and encrypts configuration values in `configuration.json` by default. Because the current Connector SDK configuration format does not define field sensitivity, the tool defaults to encrypting every field. If a user intentionally changes a field back to plaintext, `run_connector.py` and `deploy_connector.py` pass that value through unchanged; values with the `ENCRYPTED:v1:<key_id>:local-fernet:` prefix are decrypted locally.

Encrypted values are **not uploaded as encrypted blobs** by these wrapper tools. For local tests, `run_connector.py` decrypts in memory and passes runtime configuration to `fivetran debug` via a named pipe. For deployment, `deploy_connector.py` decrypts in memory and passes runtime configuration to `fivetran deploy` via a named pipe. After that point, configuration handling is Fivetran Connector SDK / Fivetran platform behavior, not this local encryption layer.

The local encryption secret currently lives under the user's profile (`~/.fivetran/csdk_master_secret` or `%USERPROFILE%\.fivetran\csdk_master_secret`) with owner-only permissions. This is not intended to be a general-purpose production secret manager. If the local secret is lost or should no longer be trusted, delete it and rerun `enter_configuration.py` to rewrite local configuration values. OS-backed protection is tracked in `TODO.md` as a future improvement to remove the Python crypto dependency and avoid managing a local secret file directly.

## Repository Layout

```
canonical/                          edit these (source of truth)
  sdk-reference.md
  workflows/{validator,generator,fixer}.md
  skills/{build,test,deploy}-connector/SKILL.md
  tools/{enter_configuration,run_connector,deploy_connector}.py
  hooks/log-skill-use.sh

claude-code/                        Claude Code plugin (mostly generated)
  .claude-plugin/plugin.json
  CLAUDE.md
  agents/connector-{validator,generator,fixer}.md
  skills/{build,test,deploy}-connector/SKILL.md
  tools/, sdk-reference.md

codex/                              Codex CLI plugin (mostly generated)
  .codex-plugin/plugin.json
  AGENTS.md
  hooks.json
  skills/{build,test,deploy}-connector/SKILL.md
  workflows/{validator,generator,fixer}.md
  tools/, sdk-reference.md

copilot/                            GitHub Copilot CLI plugin (mostly generated)
  AGENTS.md
  agents/connector-{validator,generator,fixer}.md
  skills/{build,test,deploy,evaluate}-connector/SKILL.md
  commands/{build,test,deploy,evaluate}-connector.md
  tools/, sdk-reference.md

gemini-extension.json               Gemini CLI extension manifest (root-only requirement)
GEMINI.md                           Gemini context file
commands/{build,test,deploy}-connector.toml   Gemini slash commands
agents/connector-{validator,generator,fixer}.md   Gemini agents (generated)
skills/{build,test,deploy}-connector/SKILL.md     Gemini skills (generated)
tools/                              Gemini tools (generated copy of canonical/tools/)

.claude-plugin/marketplace.json     Claude Code marketplace pointing to ./claude-code
.agents/plugins/marketplace.json    Codex marketplace pointing to ./codex
.github/plugin/marketplace.json     Copilot CLI marketplace pointing to ./copilot

```

## Development

### What to edit

Only edit files under **`canonical/`** and the agent-specific static integration files listed below. Everything else is regenerated.

| Editing... | Run after | Affects |
|---|---|---|
| `canonical/sdk-reference.md` | `bash scripts/sync-plugins.sh` | all four agents |
| `canonical/workflows/*.md` | `bash scripts/sync-plugins.sh` | Claude agents, Codex workflows, Gemini agents, Copilot agents |
| `canonical/skills/*/SKILL.md` | `bash scripts/sync-plugins.sh` | all four agents |
| `canonical/tools/*` | `bash scripts/sync-plugins.sh` | all four agents |
| `canonical/hooks/log-skill-use.sh` | `bash scripts/sync-plugins.sh` | Claude Code, Codex, Gemini |
| `README.md` | (no sync needed) | root docs |
| `GEMINI.md`, `gemini-extension.json`, `commands/*.toml`, `hooks/hooks.json` | (no sync needed) | Gemini only |
| `claude-code/CLAUDE.md`, `claude-code/README.md`, `claude-code/hooks/hooks.json` | (no sync needed) | Claude Code only |
| `codex/AGENTS.md`, `codex/README.md`, `codex/.codex-plugin/plugin.json`, `codex/hooks.json` | (no sync needed) | Codex only |
| `copilot/AGENTS.md`, `copilot/README.md`, `copilot/commands/*.md` | (no sync needed) | Copilot CLI only |

Generated files have a `<!-- GENERATED FILE — DO NOT EDIT -->` banner at the top. Edits to them will be overwritten on the next sync.

### Sync workflow

After editing a canonical file:

```bash
bash scripts/sync-plugins.sh
git add -A
git commit
```

The sync script fans canonical content out into each per-agent tree, prepending the agent's required frontmatter where applicable (e.g., Claude subagent frontmatter, Gemini agent frontmatter). Running it again on an already-synced repo produces no diff — it is safe to re-run.

#### Bumping the plugin version

The version in all plugin manifests follows the format `YYYY.M.D.N` (UTC date, no zero-padding, plus a per-day iteration counter). Version updates are **opt-in**: pass `--bump` when you want to tag a new release:

```bash
bash scripts/sync-plugins.sh --bump
git add -A
git commit
```

Without `--bump` the manifests are left untouched, which keeps routine syncs and the pre-commit hook idempotent — re-running the script never creates a spurious version diff.

### Pre-commit hook

A hook in `.githooks/pre-commit` runs `sync-plugins.sh` (without `--bump`) and fails the commit if any generated file would change — i.e., if you edited a canonical file but forgot to re-sync.

Install once per clone:

```bash
git config core.hooksPath .githooks
```

## Telemetry

This plugin collects **anonymous usage data** to help improve the product. Each time a skill is invoked, a small event is sent containing: the skill name, plugin name and version, model, status (`started`, `ok`, or `fail`), session ID, and timestamp. No prompts, code, file contents, or personal information are ever collected.

To opt out, set the following environment variable in your shell profile (`~/.zshrc`, `~/.bashrc`, etc.):

```bash
export FIVETRAN_TELEMETRY_DISABLED=1
```

## License

MIT
