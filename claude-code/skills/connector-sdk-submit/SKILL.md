---
name: connector-sdk-submit
description: Prepare a Fivetran Connector SDK contribution for a first pull request by applying the target repository's Copilot review instructions, sanitizing configuration.json, and running Black and Flake8.
argument-hint: "Connector directory name or path (e.g., 'github_connector' or './github_connector')"
---

<!--
  GENERATED FILE — DO NOT EDIT.
  Canonical source: canonical/skills/connector-sdk-submit/SKILL.md
  Regenerate with: bash scripts/sync-plugins.sh
-->

# Submit Connector SDK Contribution

Use this skill immediately before a contributor opens their first Connector SDK pull request. Its authority is the Community Connectors Copilot instruction set, applied consistently to submissions in either repository. Do not use external examples or generic Python conventions as a substitute.

## Establish the scope and authority

1. Ask for the connector directory if it was not supplied. Identify the enclosing Git repository.
2. Choose the PR destination using these repository rules:
   - Use [`fivetran/community_connectors`](https://github.com/fivetran/community_connectors) for a new, standalone connector for a specific source; or a focused bug fix, reliability/performance improvement, or documentation update to an existing Community Connector. New connectors belong in a top-level connector directory and must be listed in that repository's root `README.md`.
   - Use [`fivetran/connector_sdk`](https://github.com/fivetran/connector_sdk) for a Connector SDK template, quickstart/tutorial, reusable generic SDK pattern, platform-feature example, AI/agent guidance, or SDK repository documentation/tooling. Place examples in the repository's existing `examples/` or template structure as appropriate.
   - If the work changes both a reusable SDK example/pattern and a standalone source connector, recommend separate PRs: the reusable material to [`fivetran/connector_sdk`](https://github.com/fivetran/connector_sdk) and the source connector to [`fivetran/community_connectors`](https://github.com/fivetran/community_connectors).
   - If the files already belong to one repository, keep the PR in that repository unless the contributor explicitly wants to split or relocate the work.
3. State the selected repository and the rule that led to the decision. If none of the rules applies, ask the contributor to choose; do not guess.
4. Before reviewing or editing, read the Community Connectors versions of:
   - `.github/instructions/configuration-review.instructions.md`
   - `.github/instructions/python-review.instructions.md`
   - `.github/instructions/readme-markdown.instructions.md`
   Use the files from a checked-out [`fivetran/community_connectors`](https://github.com/fivetran/community_connectors) repository. If the contribution itself is in Community Connectors, use its local files. Otherwise, ask the contributor for the Community Connectors checkout path.
5. If the selected target repository or the Community Connectors instruction checkout is unavailable, explain the missing item in plain language and offer to obtain it. For example: “I need a local Community Connectors checkout to apply its submission rules. May I clone the upstream repository, or would you prefer to fork it first?” Wait for approval before cloning, forking, authenticating, or changing remotes.
6. Inspect the connector's changed files and its relevant files: `connector.py`, `configuration.json`, `README.md`, and dependency files. Do not inspect or print real local configuration files such as `configuration_local.json`.

## Optional connector evaluation

Before making any edits, including non-behavioral compliance edits such as comments, README formatting, placeholders, or Black formatting, ask the contributor whether they want to run the host's `evaluate-connector` skill to identify performance bottlenecks and other quality improvements.

If they agree, invoke the evaluation skill and apply only changes the contributor authorizes. Then continue with this submission skill's review-and-fix workflow on the evaluated connector. If they decline, continue directly with the review-and-fix workflow.

## Review and fix workflow

Perform the following sequence. Treat BLOCKER and REQUEST_CHANGES levels from the loaded Copilot instructions as such in the final report.

### Preserve and sanitize configuration

Parse `configuration.json` without echoing its values. Check that it is a JSON object, uses descriptive consistent keys, and that every value is a descriptive string placeholder in the form `<DESCRIPTION_HERE>`.

Also scan it for credentials, tokens, passwords, personal data, embedded-credential URLs, database connection strings, IP addresses, internal host names, base64-looking values, and JWTs. Apply the exact security and completeness checks in the loaded configuration instruction, including agreement with connector code and README.

If a real or possible credential, personal value, or any non-placeholder value is found, warn the contributor before modifying the file:

> `configuration.json` is about to be replaced with safe placeholders. Save the real values in a separate untracked local configuration file, such as `configuration_local.json`, before continuing. Do not commit that local file.

Ask for confirmation. Only after confirmation, replace tracked configuration values with specific angle-bracket placeholders that preserve each field's intended purpose. Never copy the real values into chat, source code, README examples, command output, Git history, or another tracked file. Re-parse and scan the resulting file.

### Apply the Python instructions

Review `connector.py` against the loaded Python instruction in full. This includes SDK v2 operation usage, validation, logging, imports and dependencies, schema and state handling, error handling, streaming/pagination, naming/constants, docstrings, and main block requirements.

For every `op.upsert()` and `op.checkpoint()` call, verify the immediately preceding comment block matches the required block in the loaded instruction. Add the required block when it is missing; do not invent abbreviated wording. Also preserve the instruction's required `update()` opening log statement and its main-block comments.

Make only unambiguous compliance edits. Before a change that affects connector behavior (for example, retry policy, pagination, state advancement, primary keys, or configuration validation), describe the issue and ask the contributor to approve the proposed fix. Do not claim a semantic check passed merely because it was not mechanically verifiable.

### Apply the README instructions

If `README.md` is missing, create it before reviewing the rest of the documentation. Derive the connector name, configuration keys, tables, incremental-sync behavior, dependencies, and other verifiable facts from the connector files. Ask the contributor for information that cannot be safely inferred, such as the connector overview, how credentials are obtained, API limitations, and feature claims. Do not invent product behavior, authentication steps, or external URLs.

Create the README in the structure required by the Community Connectors README instruction: one Title Case H1; Sentence case lower-level headings; required sections in the prescribed order; and optional Configuration file, Requirements file, Authentication, and Pagination sections when they apply. Include the configuration keys as safe placeholders, not real values. Then review the generated README using the same instruction.

For an existing or generated README, enforce exactly one Title Case H1 and Sentence case for every lower-level heading; do not uppercase headings. Enforce the prescribed section requirements/order, configuration and dependency documentation, authentication/pagination requirements where applicable, list style, and formatting restrictions.

Apply these Community Connectors rules in both repositories:

- The Getting started section must include the `fivetran init --template <connector-name>` command and its required explanation.
- Requirements documentation must use the general Connector SDK preinstalled-packages link rather than naming only `fivetran_connector_sdk` and `requests`.
- Use plain Markdown examples rather than quoted examples.

Keep configuration names and descriptions aligned across `configuration.json`, `connector.py`, and `README.md`. If resolving a discrepancy requires product knowledge, show the discrepancy and ask rather than guessing.

### Format and lint

Use the target repository's formatting and lint configuration when present. For a Community Connectors checkout, run its provided formatter from the repository root:

```bash
./.github/scripts/fix-python-formatting.sh
```

This script applies Black with a 99-character line length to Python files in the checkout. If the target repository does not provide that script, use Black with the repository's required line length; when no project setting specifies it, run `python3 -m black --line-length 99 <relevant Python files>`.

Before running the script, tell the contributor that it formats every Python file in the checkout and installs Black with `pip --user` when Black is missing. Ask for approval if that could change files outside the connector or modify the local Python environment.

Community Connectors does not provide a Flake8 wrapper script. Run Flake8 from the repository root so its `.flake8` configuration and per-file ignores apply, following the CI invocation:

```bash
flake8 -- <repo-relative Python paths>
```

Apply the formatter's changes. Fix clear, behavior-preserving Flake8 failures; ask before changes with behavioral or API consequences. If the formatter script, Black, or Flake8 is unavailable, report the exact command and failure without installing packages or changing the contributor's environment unless they authorize it.

## Final verification and report

After every edit, repeat applicable configuration, Python-comment, README, Black, and Flake8 checks.

Report:

- files changed and why;
- checks passed, grouped by configuration, Python, README, Black, and Flake8;
- warnings or manually reviewed items that need contributor confirmation; and
- blocking issues left unresolved.

## Pull request handoff

When the final checks pass, ask whether the contributor wants to raise the pull request. Do not commit, push, create a fork, authenticate, or create a pull request without their explicit approval.

If approved, gather a title if they have not supplied one, then create a pull request with this body only:

```markdown
### Description

<!-- Briefly explain what changed and why. Include known limitations only if relevant. -->

### Validation

<!--
For connector code changes, attach lightweight proof that the code ran successfully,
such as a screenshot of `fivetran debug` output or a short relevant log excerpt.
Remove credentials, personal data, customer information, and other sensitive values.

For documentation-only or repository-maintenance changes, briefly describe any
validation appropriate to the change. A detailed test report is not required.
-->

### Checklist

Check only the items that apply:

- [ ] **Connector code change:** I ran `fivetran debug` and attached sanitized proof of a successful run.
- [ ] **New connector:** I added a connector-level `README.md` with the relevant [template sections](https://github.com/fivetran/community_connectors/blob/main/_template_connector/README_template.md) and listed the connector in the root `README.md`.
- [ ] **All contributions:** I confirmed that the change and its validation evidence contain no credentials, personal data, customer information, or other sensitive values.

See [CONTRIBUTING.md](https://github.com/fivetran/community_connectors/blob/main/CONTRIBUTING.md) for the complete contribution requirements.
```

Do not run `fivetran debug` solely to populate this PR body; offer it separately and obtain approval first. Check only checklist items that the contributor has actually completed.
