# Changelog

Changes for the Fivetran AI coding agent tools in this repository.

## July 2026

### fivetran-connector-sdk-tools 2026.7.8.1

- Supports AI-assisted connector development in Claude Code, Codex CLI, Gemini CLI, GitHub Copilot CLI, and GitHub Copilot IDE integrations installed from source.
- Provides workflows to build, test, deploy, evaluate, fix, and migrate connectors using coding agents.
- Includes migration support for Fivetran Functions connectors, Meltano extractors or Singer taps, and Airbyte source connectors.
- Includes local tools for secure configuration entry, local connector runs, and deployment to Fivetran.
- Updated Claude Code, Codex CLI, Gemini CLI, and GitHub Copilot plugin manifests to version `2026.7.8.1`.
- Added opt-in version bumps to `scripts/sync-plugins.sh` with `--bump`.
- Kept routine syncs and the pre-commit hook idempotent by leaving versions unchanged unless `--bump` is used.
