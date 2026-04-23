# Cursor Setup

See the [main README](../../README.md#prerequisites) for prerequisites (Python, Cursor, `fivetran-connector-sdk`, Fivetran account).

### Automatic (coming soon)

```bash
fivetran ai setup --agent cursor
```

### Install script

```bash
bash scripts/install-cursor.sh /path/to/my-connector
```

Copies `coding-agents/AGENTS.md` into your connector project root. Cursor will pick it up automatically.

### Manual

```bash
cp coding-agents/AGENTS.md /path/to/my-connector/AGENTS.md
```
