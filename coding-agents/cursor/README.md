# Cursor Setup

See the [main README](../../README.md#prerequisites) for prerequisites (Python, Cursor, `fivetran-connector-sdk`, Fivetran account).

## Installation

### Automatic (Recommended)

Requires Fivetran Connector SDK v2.9 or later:

```bash
fivetran ai --setup --agent cursor
```

This downloads the latest `AGENTS.md` into your connector project directory.

### Install Script

```bash
bash scripts/install-cursor.sh /path/to/my-connector
```

Copies `coding-agents/AGENTS.md` into your connector project root. Cursor will pick it up automatically.

### Manual

```bash
cp coding-agents/AGENTS.md /path/to/my-connector/AGENTS.md
```

## Usage

Once `AGENTS.md` is in your connector project:
1. Open the project in Cursor
2. Cursor automatically loads the agent instructions
3. Ask Cursor to help you build, test, or fix your connector
