# Changelog

AI-assisted tooling changes for building, testing, and deploying Fivetran Connector SDK connectors.

This changelog is based on the Fivetran Connector SDK release notes and includes only changes related to AI coding agents, agent plugins, and setup/tooling flows for this repository.

## August 2026

### `fivetran-connector-sdk` 2.11.0

- Updated `fivetran init` and AI plugin setup behavior for existing projects.
- Introduced the `--yes` flag and updated other non-interactive flags for clearer automated setup flows.

## July 2026

### `fivetran-connector-sdk` 2.10.1

- Improved logging for agent plugins.

## June 2026

### `fivetran-connector-sdk` 2.9.1

- Added Copilot plugin support to `fivetran init`, allowing users to configure AI-assisted connector development with GitHub Copilot.
- Deprecated the `--force` and `-f` flags and introduced `--non-interactive` for clearer unattended setup behavior.
- Updated the CLI to point to renamed plugin repositories.

### `fivetran-connector-sdk` 2.9.0

- Updated `fivetran init` to install the `fivetran-connector-sdk@fivetran-connector-sdk-ai` plugin, which provides AI-powered features for connector development.

## November 2025

### `fivetran-connector-sdk` 2.3.5

- Added the `fivetran init` command for initializing projects, including the option to configure Fivetran Connector SDK context for the user's AI agent of choice.
