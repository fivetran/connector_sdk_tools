# Fivetran Connector Builder — Claude Code Plugin

Build, test, fix, and deploy Fivetran connectors with AI assistance, directly in Claude Code.

## Prerequisites
- Python 3.10-3.14
- [Claude Code](https://claude.com/claude-code) installed
- [Fivetran Connector SDK](https://pypi.org/project/fivetran-connector-sdk/) — `pip install fivetran-connector-sdk`
- A Fivetran account (https://fivetran.com)

## Installation

See the [top-level README](../README.md#install) for the full install matrix. Quick path:

```bash
claude plugin marketplace add fivetran/connector_sdk_tools
claude plugin install fivetran-connector-sdk@fivetran-connector-sdk-ai
```

Or from inside a Claude Code session:

```
/plugin marketplace add fivetran/connector_sdk_tools
/plugin install fivetran-connector-sdk@fivetran-connector-sdk-ai
```

### Post-installation

Install the tool dependencies:

macOS/Linux:
```bash
pip install -r /path/to/claude-code/tools/requirements.txt
```

Windows PowerShell:
```powershell
python -m pip install -r "C:\path\to\claude-code\tools\requirements.txt"
```

## Quick Start Tutorial

### Step 1: Start Claude Code with the Plugin

```bash
cd ~/my-connectors  # or wherever you want to create connectors
claude --plugin-dir /path/to/claude-code
```

### Step 2: Build Your First Connector

In the Claude Code chat, describe the connector you want to build:

```
/build-connector <describe your data source and what tables you want to sync>
```

Claude will:
1. Research the API documentation
2. Ask you clarifying questions about scope and data requirements
3. Generate the connector code
4. Set up a Python virtual environment
5. Ask you to enter your API credentials

### Step 3: Enter Your API Credentials
When prompted, open a **separate terminal** and run:

macOS/Linux:
```bash
cd ~/my-connectors/your_connector
python -m pip install -r /path/to/claude-code/tools/requirements.txt
python /path/to/claude-code/tools/enter_configuration.py configuration.json
```

Windows PowerShell:
```powershell
cd "C:\path\to\my-connectors\your_connector"
python -m pip install -r "C:\path\to\claude-code\tools\requirements.txt"
python "C:\path\to\claude-code\tools\enter_configuration.py" "configuration.json"
```

Enter your API credentials when prompted. They are encrypted immediately into the top-level `encrypted` field in `configuration.json` — Claude never sees them. The original placeholder fields remain as the recoverable baseline.

The dependency install is temporary. Once secure configuration entry is available in the Fivetran Connector SDK CLI, this helper script flow will be replaced.

**First time only:** The tool creates a local encryption secret under your user profile (`~/.fivetran/csdk_master_secret` on macOS/Linux, `%USERPROFILE%\.fivetran\csdk_master_secret` on Windows) and uses it immediately. Claude never sees the secret or plaintext credentials.

Only `enter_configuration.py` creates the secret. The test and deploy tools require the existing secret so they can decrypt the `encrypted` field. To start credential entry over, delete the `encrypted` field from `configuration.json` and run `enter_configuration.py` again.

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
- Run `/test-connector` anytime to re-test
- Run `/deploy-connector` when ready to deploy to Fivetran

### Example Session

```
You: /build-connector <Your API> connector for <tables you want>

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
/build-connector Stripe API connector for payments, customers, and invoices
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
python -m pip install -r /path/to/claude-code/tools/requirements.txt
python /path/to/claude-code/tools/enter_configuration.py configuration.json
```

On first run, it creates a local encryption secret under your user profile. This encrypts your credentials so the AI cannot see them.

### Test a Connector
```
/test-connector
```

Runs `fivetran debug`, checks `warehouse.db` for synced data, and reports results.

### Fix or Modify a Connector

Just describe the problem or change in natural language — no slash command needed:

```
I'm getting an authentication error: Invalid API key
```

or

```
Add a "pull requests" table to my GitHub connector
```

The plugin routes to the `connector-fixer` subagent, which classifies the error (INFRA / FIRST_RUN / CODE), researches the correct SDK pattern, and applies targeted fixes to `connector.py`.

### Deploy a Connector
```
/deploy-connector
```

Validates, runs a final test, and guides you through Fivetran deployment.

## What's Included

| Component | Description |
|-----------|-------------|
| `/build-connector` | Full generation workflow (research → generate → test → auto-fix) |
| `/test-connector` | Run and validate connector tests |
| `/deploy-connector` | Package and deploy to Fivetran |
| `agents/connector-validator.md` | Subagent for API research and requirements gathering |
| `agents/connector-generator.md` | Subagent for generating connector code |
| `agents/connector-fixer.md` | Subagent for diagnosing and fixing errors (invoked automatically on natural-language fix requests) |
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
