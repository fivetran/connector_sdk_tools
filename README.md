# Fivetran Connector SDK - AI Tools

AI-powered tools for building, testing, and deploying [Fivetran Connector SDK](https://fivetran.com/docs/connector-sdk) connectors.

## Repository Structure

```
coding-agents/
  AGENTS.md              # Shared instructions for all agents (single source of truth)
  claude-code/           # Claude Code plugin (flagship) — skills, subagents, secure tools
  cursor/                # Cursor setup
  windsurf/              # Windsurf setup
  vscode-copilot/        # VS Code + GitHub Copilot setup
  codex/                 # OpenAI Codex CLI setup
  gemini-cli/            # Google Gemini CLI setup
csdk-ai-builder-app/    # Web-based connector builder (React + FastAPI)
```

## Quick Start

### Claude Code (recommended)

Install the plugin from this marketplace:

```bash
/plugin marketplace add fivetran/fivetran_csdk_tools
/plugin install fivetran-csdk
```

Then use the slash commands in any connector project:

- `/build-connector` — Research an API and generate a complete connector
- `/test-connector` — Run and validate your connector locally
- `/fix-connector` — Diagnose and fix errors automatically
- `/deploy-connector` — Deploy to Fivetran

### Cursor / Windsurf / VS Code + Copilot / Codex

Copy `coding-agents/AGENTS.md` into your connector project root as `AGENTS.md`:

```bash
cp coding-agents/AGENTS.md /path/to/my-connector/AGENTS.md
```

### Gemini CLI

Copy `coding-agents/AGENTS.md` into your connector project root as `GEMINI.md`:

```bash
cp coding-agents/AGENTS.md /path/to/my-connector/GEMINI.md
```

### Web App

See [csdk-ai-builder-app/README.md](csdk-ai-builder-app/README.md) for setup and deployment instructions.

## Coming Soon

`fivetran ai setup` — automatic installation and configuration for all supported coding agents, integrated into the Fivetran CLI.

## License

MIT
