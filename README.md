# Fivetran Connector SDK - AI Tools

AI-powered tools for building, testing, and deploying [Fivetran Connector SDK](https://fivetran.com/docs/connector-sdk) connectors.

## Repository Structure

```
coding-agents/          # AI coding agent integrations
  claude-code/           # Claude Code plugin (flagship) — skills, subagents, secure tools
  cursor/                # Cursor instruction files
  windsurf/              # Windsurf instruction files
  vscode-copilot/        # VS Code + GitHub Copilot instruction files
tutorials/              # Step-by-step tutorials for building connectors with AI
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

### Cursor / Windsurf / VS Code + Copilot

Copy the appropriate `AGENTS.md` file from `coding-agents/<your-tool>/` into your connector project root. The AI agent will pick up the Fivetran SDK instructions automatically.

### Web App

See [csdk-ai-builder-app/README.md](csdk-ai-builder-app/README.md) for setup and deployment instructions.

## Coming Soon

`fivetran ai setup` — automatic installation and configuration for all supported coding agents, integrated into the Fivetran CLI.

## License

MIT
