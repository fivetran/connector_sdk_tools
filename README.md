# Fivetran Connector SDK - AI Tools

AI-powered tools for building, testing, and deploying [Fivetran Connector SDK](https://fivetran.com/docs/connector-sdk) connectors.

## Repository Structure

```
.claude-plugin/marketplace.json    # Claude Code marketplace
.agents/plugins/marketplace.json   # Codex marketplace
scripts/                            # Install helpers + internal sync
coding-agents/
  AGENTS.md                         # Shared instructions for non-plugin agents
  sdk-reference.md                  # Canonical SDK rules and patterns
  workflows/                        # Canonical role prompts (validator, generator, fixer)
  claude-code/                      # Claude Code plugin — skills, subagents, hooks, tools
  codex/                            # Codex CLI plugin — skills, tools
  cursor/ gemini-cli/              # Setup instructions per agent
```

## Prerequisites

Before installing, the user must have:

- **Python 3.10–3.14**
- **A coding agent** (Claude Code, Codex CLI, Cursor, or Gemini CLI)
- **Fivetran Connector SDK** — `pip install fivetran-connector-sdk` (provides the `fivetran` CLI and the `fivetran ai` bootstrap command)
- **A Fivetran account** (signup: https://fivetran.com)

Once those are in place, `fivetran ai` configures the user's chosen coding agent and installs the plugin/skills below.

## Quick Start

Each agent uses its native install flow where available. Install scripts in `scripts/` wrap the manual steps.

### Claude Code

In a Claude Code session, from GitHub:

```
/plugin marketplace add fivetran/fivetran_csdk_tools
/plugin install fivetran-connector-sdk@fivetran-connector-sdk-tools
```

Or from a local clone:

```
/plugin marketplace add /path/to/fivetran_csdk_tools
/plugin install fivetran-connector-sdk@fivetran-connector-sdk-tools
```

Or run `bash scripts/install-claude-code.sh` to see the full commands.

Skills: `/build-connector`, `/test-connector`, `/deploy-connector`. (Code fixes are handled in natural language — the agent invokes the `connector-fixer` subagent automatically.)

### Codex CLI

```bash
bash scripts/install-codex.sh
```

Prints step-by-step install instructions (enable plugins feature flag, add marketplace, install plugin). See [coding-agents/codex/README.md](coding-agents/codex/README.md) for details.

Skills appear in the `$` popup: `$build_connector`, `$test_connector`, `$deploy_connector`. (Code fixes are handled in natural language — the plugin guides the agent through the fixer workflow.)

### Cursor

```bash
bash scripts/install-cursor.sh /path/to/my-connector
```

Copies `coding-agents/AGENTS.md` into your project. Cursor picks it up automatically.

### Gemini CLI

```bash
bash scripts/install-gemini-cli.sh /path/to/my-connector
```

Copies `coding-agents/AGENTS.md` → `GEMINI.md`.

## For Maintainers

Canonical content (edit these):
- `coding-agents/sdk-reference.md` — SDK rules and patterns
- `coding-agents/workflows/{validator,generator,fixer}.md` — role prompts
- `coding-agents/claude-code/tools/` — Python credential and runner tools

Generated content (do NOT edit; regenerate with `bash scripts/sync-plugins.sh`):
- `coding-agents/claude-code/sdk-reference.md`
- `coding-agents/claude-code/agents/connector-{validator,generator,fixer}.md`
- `coding-agents/codex/sdk-reference.md`
- `coding-agents/codex/tools/*`

Run `bash scripts/sync-plugins.sh` after editing canonical sources.

## fivetran ai Command

The `fivetran ai` command is now available in Fivetran Connector SDK v2.9+ for automatic installation and configuration of all supported coding agents.

### Quick Install

```bash
# Install an agent
fivetran ai --setup --agent <agent-name>

# Examples
fivetran ai --setup --agent claude-code
fivetran ai --setup --agent cursor
fivetran ai --setup --agent codex
fivetran ai --setup --agent gemini-cli

# Update agents
fivetran ai --update

# List available agents
fivetran ai --list
```

For detailed usage, see individual agent setup instructions above.

## License

MIT
