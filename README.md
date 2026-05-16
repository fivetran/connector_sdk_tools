AI-assisted tools for building, testing, and deploying [Fivetran Connector SDK](https://fivetran.com/docs/connector-sdk) connectors. Distributed as a native plugin/extension for Claude Code, Codex CLI, and Gemini CLI.

## Prerequisites

- **Python 3.10–3.14**
- **A supported coding agent** (Claude Code, Codex CLI, or Gemini CLI — see install matrix below)
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
claude plugin marketplace add fivetran/fivetran_csdk_tools
claude plugin install fivetran-connector-sdk@fivetran-connector-sdk-tools
```

Or from inside a Claude Code session:

```
/plugin marketplace add fivetran/fivetran_csdk_tools
/plugin install fivetran-connector-sdk@fivetran-connector-sdk-tools
```

See [`claude-code/README.md`](claude-code/README.md) for the full tutorial.

### Codex CLI

```bash
codex plugin marketplace add fivetran/fivetran_csdk_tools
codex plugin install fivetran-connector-sdk@fivetran-connector-sdk-tools
```

Plugins must also be enabled in `~/.codex/config.toml`. See [`codex/README.md`](codex/README.md) for the full setup.

### Gemini CLI

```bash
gemini extensions install https://github.com/fivetran/fivetran_csdk_tools
```

For non-interactive use (e.g., scripts):

```bash
gemini extensions install https://github.com/fivetran/fivetran_csdk_tools --consent --skip-settings
```

## Usage

Once installed, in your connector project directory:

| Command | Purpose |
|---------|---------|
| `/build-connector` | Research an API and generate a new connector |
| `/test-connector` | Run and validate an existing connector locally |
| `/deploy-connector` | Deploy a connector to your Fivetran account |

For code fixes or modifications, describe the problem in natural language — the agent routes to the `connector-fixer` subagent automatically.

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
  hooks/hooks.json
  tools/, sdk-reference.md, native-connectors.md

codex/                              Codex CLI plugin (mostly generated)
  .codex-plugin/plugin.json
  AGENTS.md
  skills/{build,test,deploy}-connector/SKILL.md
  workflows/{validator,generator,fixer}.md
  tools/, sdk-reference.md, native-connectors.md

gemini-extension.json               Gemini CLI extension manifest (root-only requirement)
GEMINI.md                           Gemini context file
commands/{build,test,deploy}-connector.toml   Gemini slash commands
agents/connector-{validator,generator,fixer}.md   Gemini agents (generated)
skills/{build,test,deploy}-connector/SKILL.md     Gemini skills (generated)
tools/                              Gemini tools (generated copy of canonical/tools/)

.claude-plugin/marketplace.json     Claude Code marketplace pointing to ./claude-code
.agents/plugins/marketplace.json    Codex marketplace pointing to ./codex
```

## Development

### What to edit

Only edit files under **`canonical/`** and the static Gemini files at the root (`gemini-extension.json`, `GEMINI.md`, `commands/*.toml`). Everything else is regenerated.

| Editing... | Run after | Affects |
|---|---|---|
| `canonical/sdk-reference.md` | `bash scripts/sync-plugins.sh` | all three agents |
| `canonical/native-connectors.md` | `bash scripts/sync-plugins.sh` | all three agents |
| `canonical/workflows/*.md` | `bash scripts/sync-plugins.sh` | Claude agents, Codex workflows, Gemini agents |
| `canonical/skills/*/SKILL.md` | `bash scripts/sync-plugins.sh` | all three agents |
| `canonical/tools/*` | `bash scripts/sync-plugins.sh` | all three agents |
| `GEMINI.md`, `gemini-extension.json`, `commands/*.toml` | (no sync needed) | Gemini only |
| `claude-code/CLAUDE.md`, `claude-code/hooks/hooks.json` | (no sync needed) | Claude Code only |
| `codex/AGENTS.md`, `codex/.codex-plugin/plugin.json` | (no sync needed) | Codex only |

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
