# Claude Code Directives

0. Do not add new directives to this file unless explicitly told to do so.

1. **Client-side storage** - STOP and ASK before using localStorage, sessionStorage, or cookies.

2. **Fallback implementation** - STOP and ASK before adding any workaround, fallback, or graceful degradation code.

3. **Scope creep** - STOP and ASK before implementing anything extra not directly requested. When in doubt, ask.

4. **Think through implications** - Before implementing, think through all implications: all code paths (success, error, edge cases), all related state that needs updating together, all ways users can trigger the code, and what happens to existing state. Don't implement partial solutions.

5. **Do NOT overengineer** - Consider if the dead simple solution will satisfy the request first.

6. **Use tests to debug and fix issues** - Write tests FIRST to understand and reproduce bugs. These tests then serve as regression tests.
