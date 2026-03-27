# Fivetran Connector Builder - Coding Agent Plugins

AI-powered tools for building Fivetran connectors, available for multiple coding agents.

## Supported Agents

| Agent | Folder | Status |
|-------|--------|--------|
| [Claude Code](https://claude.ai/code) | `claude-code/` | Ready |

## What The Plugins Do

These plugins add Fivetran Connector SDK expertise to your AI coding assistant:

1. **Build** (`/build-connector`) - Research API docs, validate requirements, and generate production-ready connector code
2. **Test** (`/test-connector`) - Run the connector with secure credential handling and verify results
3. **Fix** (automatic) - Diagnose and fix connector errors, distinguishing code bugs from config issues
4. **Deploy** (`/deploy-connector`) - Package and deploy the connector to Fivetran

## Installation

### Claude Code

1. Download the plugin zip and unzip it
2. Install the plugin:

```bash
claude plugin install --plugin-dir ./path/to/your/plugin/folder
```

Or load it for a single session without installing:

```bash
claude --plugin-dir ./path/to/your/plugin/folder
```

## Quick Start

1. **Build** - `/build-connector Stripe API connector for payments and customers`
   - The AI researches the API docs, asks clarifying questions, then generates `connector.py`, `configuration.json`, and `README.md`

2. **Test** - `/test-connector`
   - Prompts you to enter credentials securely, runs the connector, and reports results

3. **Fix** - If tests fail with a code error, the AI automatically diagnoses and fixes the issue

4. **Deploy** - `/deploy-connector`
   - Packages and deploys the connector to Fivetran

## Prerequisites

- Python 3.9+
- [Fivetran Connector SDK](https://pypi.org/project/fivetran-connector-sdk/)
- API documentation for your data source

## Contributing

To add support for another coding agent, create a new folder with the appropriate plugin/skill format for that agent. The core prompts in `claude-code/agents/` can be adapted.
