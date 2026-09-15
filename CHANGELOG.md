# Changelog

Changes for the Fivetran AI coding agent tools in this repository.

## September 2026

### fivetran-connector-sdk-tools 2026.9.12.1

- Centralized example discovery in sdk-reference.md to eliminate duplication across agent and workflow documentation.
- Replaced hardcoded URLs and file paths in connector-fixer, connector-generator, and connector-validator agents with topic-based guidance that defers to a single source of truth.
- Removed redundant "EXAMPLE CATEGORIZATION GUIDE" sections from agents and workflows, streamlining maintenance and reducing outdated reference links.

## July 2026

### fivetran-connector-sdk-tools 2026.7.8.1

- Supports AI-assisted connector development in Claude Code, Codex CLI, Gemini CLI, GitHub Copilot CLI, and GitHub Copilot IDE integrations installed from source.
- Provides workflows to build, test, deploy, evaluate, fix, and migrate connectors using coding agents.
- Includes migration support for Fivetran Functions connectors, Meltano extractors or Singer taps, and Airbyte source connectors.
- Includes local tools for secure configuration entry, local connector runs, and deployment to Fivetran.
- Updated Claude Code, Codex CLI, Gemini CLI, and GitHub Copilot plugin manifests to version `2026.7.8.1`.
