# Plan: Shared Prompts Between Webapp and Plugin

## Goal
Maintain agent prompts in one place instead of two. Currently the webapp (`backend/app/`) and plugin (`fivetran-connector-builder/agents/`) have separate copies that drift apart.

## Current State
- Validation: webapp 229 lines, plugin 123 lines — close enough to unify now
- Generator: webapp 440 lines, plugin 94 lines — very different, needs reconciliation first
- Fixer: webapp 222 lines, plugin 104 lines — different, needs reconciliation

## Approach
1. Shared source of truth lives in `shared/prompts/` (validation.md, generator.md, fixer.md)
2. A sync script generates both targets:
   - **Webapp** (`backend/app/`): prepends webapp-specific header (template vars like `{{CONNECTOR_DESCRIPTION}}`, `<analysis>` tag instructions)
   - **Plugin** (`fivetran-connector-builder/agents/`): prepends YAML frontmatter (name, description, tools, model, maxTurns)
3. Add an npm script: `npm run sync-prompts`

## Key Differences to Handle

### Webapp-only (prepended by sync script)
- Template variable injection: `{{CONNECTOR_DESCRIPTION}}`
- `<analysis>` tag instructions for structured thinking
- Formatting requirement for nested markdown lists

### Plugin-only (prepended by sync script)
- YAML frontmatter: name, description, tools, model, maxTurns, permissionMode

### Shared (lives in shared/prompts/)
- Core domain knowledge (SDK rules, constraints)
- Responsibilities (research, gather requirements, ask questions)
- Output format (complete spec format, incomplete spec format)
- Examples (good vs bad output)
- Validation workflow phases

## TODO
- [x] Create `shared/prompts/validation.md` (done — core validation prompt extracted)
- [ ] Create sync script (`scripts/sync-prompts.sh`)
- [ ] Reconcile generator prompts (webapp is 4x larger — decide what to keep)
- [ ] Reconcile fixer prompts (webapp is 2x larger)
- [ ] Create `shared/prompts/generator.md` and `shared/prompts/fixer.md`
- [ ] Update webapp backend to read from generated files (or keep current paths)
- [ ] Test both webapp and plugin with synced prompts
