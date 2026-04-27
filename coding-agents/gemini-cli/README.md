# Google Gemini CLI Setup

See the [main README](../../README.md#prerequisites) for prerequisites (Python, Gemini CLI, `fivetran-connector-sdk`, Fivetran account).

## Installation

### Automatic (Recommended)

Requires Fivetran Connector SDK v2.9 or later:

```bash
fivetran ai --setup --agent gemini-cli
```

This downloads the latest agent instructions as `GEMINI.md` into your connector project directory.

### Install Script

```bash
bash scripts/install-gemini-cli.sh /path/to/my-connector
```

Copies `coding-agents/AGENTS.md` into your connector project root as `GEMINI.md`. Gemini CLI will pick it up automatically.

### Manual

```bash
cp coding-agents/AGENTS.md /path/to/my-connector/GEMINI.md
```

## Usage

Once `GEMINI.md` is in your connector project:
1. Gemini CLI automatically loads the agent instructions
2. Ask Gemini to help you build, test, or fix your connector
