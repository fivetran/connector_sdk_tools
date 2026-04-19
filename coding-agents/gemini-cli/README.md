# Google Gemini CLI Setup

### Automatic (coming soon)

```bash
fivetran ai setup --agent gemini-cli
```

### Install script

```bash
bash scripts/install-gemini-cli.sh /path/to/my-connector
```

Copies `coding-agents/AGENTS.md` into your connector project root as `GEMINI.md`. Gemini CLI will pick it up automatically.

### Manual

```bash
cp coding-agents/AGENTS.md /path/to/my-connector/GEMINI.md
```
