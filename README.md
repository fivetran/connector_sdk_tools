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
  cursor/ windsurf/ vscode-copilot/ gemini-cli/    # Setup instructions per agent
csdk-ai-builder-app/                # Web-based connector builder (React + FastAPI)
```

## Quick Start

Each agent uses its native install flow where available. Install scripts in `scripts/` wrap the manual steps.

### Claude Code

```bash
# In a Claude Code session:
/plugin marketplace add fivetran/fivetran_csdk_tools
/plugin install fivetran-csdk
```

Or run `bash scripts/install-claude-code.sh` to see the full commands.

Skills: `/build-connector`, `/test-connector`, `/fix-connector`, `/deploy-connector`.

### Codex CLI

```bash
bash scripts/install-codex.sh
```

Prints step-by-step install instructions (enable plugins feature flag, add marketplace, install plugin). See [coding-agents/codex/README.md](coding-agents/codex/README.md) for details.

Skills appear in the `$` popup: `$build_connector`, `$test_connector`, `$fix_connector`, `$deploy_connector`.

### Cursor / Windsurf / VS Code + Copilot

```bash
bash scripts/install-cursor.sh /path/to/my-connector
# or install-windsurf.sh / install-vscode-copilot.sh
```

Copies `coding-agents/AGENTS.md` into your project. The agent picks it up automatically.

### Gemini CLI

```bash
bash scripts/install-gemini-cli.sh /path/to/my-connector
```

Copies `coding-agents/AGENTS.md` → `GEMINI.md`.

### Web App

See [csdk-ai-builder-app/README.md](csdk-ai-builder-app/README.md) for setup and deployment instructions.

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

## Coming Soon

`fivetran ai setup` — automatic installation and configuration for all supported coding agents, integrated into the Fivetran CLI.

## License

MIT
