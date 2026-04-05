# Fivetran Connector Builder — Claude Code Plugin

Build, test, fix, and deploy Fivetran connectors with AI assistance, directly in Claude Code.

## Prerequisites
- [Claude Code](https://claude.com/claude-code) installed
- Python 3.10-3.14
- [Fivetran Connector SDK](https://pypi.org/project/fivetran-connector-sdk/)

## Installation

### Automatic (coming soon)

```bash
fivetran ai setup --agent claude-code
```

### Via marketplace

```bash
/plugin marketplace add fivetran/fivetran_csdk_tools
/plugin install fivetran-csdk
```

### Manual

```bash
claude install-plugin /path/to/coding-agents/claude-code
```

Or load for a single session:

```bash
claude --plugin-dir /path/to/coding-agents/claude-code
```

### Post-installation
Install the tool dependencies:
```bash
pip install -r /path/to/coding-agents/claude-code/tools/requirements.txt
```

## Quick Start Tutorial

### Step 1: Start Claude Code with the Plugin

```bash
cd ~/my-connectors  # or wherever you want to create connectors
claude --plugin-dir /path/to/coding-agents/claude-code
```

### Step 2: Build Your First Connector

In the Claude Code chat, describe the connector you want to build:

```
/fivetran-csdk:build-connector <describe your data source and what tables you want to sync>
```

Claude will:
1. Research the API documentation
2. Ask you clarifying questions about scope and data requirements
3. Generate the connector code
4. Set up a Python virtual environment
5. Ask you to enter your API credentials

### Step 3: Enter Your API Credentials
When prompted, open a **separate terminal** and run:

```bash
cd ~/my-connectors/<your_connector>
python /path/to/coding-agents/claude-code/tools/enter_configuration.py configuration.json
```

Enter your API credentials when prompted. They are encrypted immediately — Claude never sees them.

**First time only:** If `CSDKAI_MASTER_SECRET` is not set, the tool will generate one for you and show instructions to add it to your shell config (e.g., `~/.zshrc`). Add the line, reload your shell, and run the tool again.

Go back to Claude Code and tell it you've entered your credentials.

### Step 4: Test the Connector

Claude will automatically run the first test. If it succeeds, you'll see:
- Tables synced
- Row counts for each table
- Sample data

If it fails, Claude will diagnose the issue:
- **INFRA error**: Network/infrastructure problem
- **FIRST_RUN error**: Likely a credentials or config issue — verify your API credentials
- **CODE error**: Claude will automatically fix the code and re-test

### Step 5: Iterate and Deploy

Once testing passes, you can:
- Ask Claude to add more tables or features
- Run `/fivetran-csdk:test-connector` anytime to re-test
- Run `/fivetran-csdk:deploy-connector` when ready to deploy to Fivetran

### Example Session

```
You: /fivetran-csdk:build-connector <Your API> connector for <tables you want>

Claude: I'll build a connector for <Your API>. Let me research the API...
        [researches API docs]

        I have a few questions:
        1. <clarifying question about scope>
        2. <clarifying question about filtering>

You: <your answers>

Claude: Got it. Let me generate the connector...
        [creates <your_connector>/ directory with connector.py, configuration.json, README.md]
        [sets up virtual environment]

        Please enter your API credentials. In a separate terminal, run:
          python .../enter_configuration.py configuration.json

You: Done, I've entered my credentials

Claude: Running the connector test...
        [runs fivetran debug]

        ✅ Test passed!
        Tables synced:
          - <table_1>: X rows
          - <table_2>: Y rows

        Your connector is ready. Would you like to deploy it to Fivetran?
```

## Usage

### Build a New Connector
```
/fivetran-csdk:build-connector Stripe API connector for payments, customers, and invoices
```

This will:
1. Research the API documentation
2. Ask clarifying questions if needed
3. Generate connector code following SDK best practices
4. Set up a virtual environment
5. Run an initial test
6. Auto-fix any code errors
7. Prompt you to enter configuration values (API credentials)

### Entering Configuration Values

After the connector is generated, you'll need to enter your API credentials. Run this in a **separate terminal**:

```bash
python /path/to/coding-agents/claude-code/tools/enter_configuration.py configuration.json
```

On first run, it will generate an encryption secret and show you the command to add to your shell config. This encrypts your credentials so the AI cannot see them.

### Test a Connector
```
/fivetran-csdk:test-connector
```

Runs `fivetran debug`, checks `warehouse.db` for synced data, and reports results.

### Fix a Failing Connector
```
/fivetran-csdk:fix-connector Getting authentication error: Invalid API key
```

Classifies the error (credentials vs code), and either guides you on configuration or fixes the code automatically.

### Deploy a Connector
```
/fivetran-csdk:deploy-connector
```

Validates, runs a final test, and guides you through Fivetran deployment.

## What's Included

| Component | Description |
|-----------|-------------|
| `/fivetran-csdk:build-connector` | Full generation workflow (research → generate → test → fix) |
| `/fivetran-csdk:test-connector` | Run and validate connector tests |
| `/fivetran-csdk:fix-connector` | Diagnose and fix connector errors |
| `/fivetran-csdk:deploy-connector` | Package and deploy to Fivetran |
| `agents/connector-generator.md` | Subagent for generating connector code |
| `agents/connector-validator.md` | Subagent for validating connector output |
| `agents/connector-fixer.md` | Subagent for diagnosing and fixing errors |
| Hooks | Auto-reminder to test after code changes |
| `tools/enter_configuration.py` | Enter and encrypt API credentials |
| `tools/run_connector.py` | Run connector with encrypted config (decrypts via named pipe) |
| `tools/deploy_connector.py` | Deploy connector with encrypted config |

## How It Works

This plugin turns Claude Code into a Fivetran connector development tool by injecting:

1. **Domain knowledge** — Fivetran SDK patterns, best practices, and common pitfalls
2. **Workflow skills** — Step-by-step processes for building, testing, fixing, and deploying
3. **Specialized agents** — Subagents focused on research, generation, and debugging
4. **SDK examples** — Automatic fetching of relevant patterns from the official examples repo

Claude Code provides the AI conversation, file editing, terminal access, and git integration. This plugin adds the Fivetran-specific expertise on top.
