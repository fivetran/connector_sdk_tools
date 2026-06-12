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

`fivetran init` scaffolds a new connector project and offers to configure a coding agent for you — detecting which of Claude Code, Codex CLI, or Gemini CLI you have installed and running the relevant plugin install command on your behalf. You can also skip the agent setup if you'd rather install it yourself; see the matrix below.

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

## Usage

Once installed, in your connector project directory:

| Command (Claude Code / Gemini CLI / Copilot CLI) | Codex CLI | Purpose |
|---|---|---|
| `/fivetran-connector-sdk:build-connector` | `$build_connector` | Research an API and generate a new connector |
| `/fivetran-connector-sdk:test-connector` | `$test_connector` | Run and validate an existing connector locally |
| `/fivetran-connector-sdk:deploy-connector` | `$deploy_connector` | Deploy a connector to your Fivetran account |

For code fixes or modifications, describe the problem in natural language — the agent routes to the `connector-fixer` subagent automatically.

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
  native-connectors.md
  workflows/{validator,generator,fixer}.md
  skills/{build,test,deploy}-connector/SKILL.md
  tools/{enter_configuration,run_connector,deploy_connector}.py

claude-code/                        Claude Code plugin (mostly generated)
  .claude-plugin/plugin.json
  CLAUDE.md
  agents/connector-{validator,generator,fixer}.md
  skills/{build,test,deploy}-connector/SKILL.md
  tools/, sdk-reference.md, native-connectors.md

codex/                              Codex CLI plugin (mostly generated)
  .codex-plugin/plugin.json
  AGENTS.md
  skills/{build,test,deploy}-connector/SKILL.md
  workflows/{validator,generator,fixer}.md
  tools/, sdk-reference.md, native-connectors.md

copilot/                            GitHub Copilot CLI plugin (mostly generated)
  AGENTS.md
  agents/connector-{validator,generator,fixer}.md
  skills/{build,test,deploy,evaluate}-connector/SKILL.md
  commands/{build,test,deploy,evaluate}-connector.md
  tools/, sdk-reference.md, native-connectors.md

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

Only edit files under **`canonical/`** and the static Gemini files at the root (`gemini-extension.json`, `GEMINI.md`, `commands/*.toml`). Everything else is regenerated.

| Editing... | Run after | Affects |
|---|---|---|
| `canonical/sdk-reference.md` | `bash scripts/sync-plugins.sh` | all four agents |
| `canonical/native-connectors.md` | `bash scripts/sync-plugins.sh` | all four agents |
| `canonical/workflows/*.md` | `bash scripts/sync-plugins.sh` | Claude agents, Codex workflows, Gemini agents, Copilot agents |
| `canonical/skills/*/SKILL.md` | `bash scripts/sync-plugins.sh` | all four agents |
| `canonical/tools/*` | `bash scripts/sync-plugins.sh` | all four agents |
| `GEMINI.md`, `gemini-extension.json`, `commands/*.toml` | (no sync needed) | Gemini only |
| `claude-code/CLAUDE.md` | (no sync needed) | Claude Code only |
| `codex/AGENTS.md`, `codex/.codex-plugin/plugin.json` | (no sync needed) | Codex only |
| `copilot/AGENTS.md`, `copilot/commands/*.md` | (no sync needed) | Copilot CLI only |

Generated files have a `<!-- GENERATED FILE — DO NOT EDIT -->` banner at the top. Edits to them will be overwritten on the next sync.

### Sync workflow

After editing a canonical file:

```bash
bash scripts/sync-plugins.sh
git add -A
git commit
```

The sync script fans canonical content out into each per-agent tree, prepending the agent's required frontmatter where applicable (e.g., Claude subagent frontmatter, Gemini agent frontmatter).

### Pre-commit hook

A hook in `.githooks/pre-commit` runs `sync-plugins.sh` and fails the commit if any generated file would change — i.e., if you edited a canonical file but forgot to re-sync.

Install once per clone:

```bash
git config core.hooksPath .githooks
```

## License

MIT
