---
name: connector-sdk-submit
description: Prepare a Community Connector or Fivetran Connector SDK example for a first pull request by applying the target repository's GitHub review instructions, sanitizing configuration.json, and running Black and Flake8.
argument-hint: "Connector directory name or path (e.g., 'github_connector' or './github_connector')"
---

# Submit Connector SDK Contribution

Use this skill immediately before a contributor opens their first Connector SDK example-connector pull request. Its authority is the selected target repository's GitHub review instructions under `.github/instructions`. Do not use external examples or generic Python conventions as a substitute.

## Establish the scope and authority

1. Ask for the connector directory if it was not supplied. Identify the enclosing Git repository.
2. Choose the PR destination using these repository rules:
   - Use [`fivetran/community_connectors`](https://github.com/fivetran/community_connectors) for a new, standalone connector for a specific source; or a focused bug fix, reliability/performance improvement, or documentation update to an existing Community Connector. New connectors belong in a top-level connector directory and must be listed in that repository's root `README.md`.
   - Use [`fivetran/connector_sdk`](https://github.com/fivetran/connector_sdk) for a Connector SDK template, quickstart/tutorial, reusable generic SDK pattern. Place examples in the repository's existing `examples/`.
   - If the work could be treated as either a reusable SDK example/pattern or a standalone source connector, prioritize [`fivetran/community_connectors`](https://github.com/fivetran/community_connectors). Submit the standalone connector there; do not split the work or create PRs in both repositories.
   - If the files already belong to one repository, keep the PR in that repository.
3. State the selected repository and the rule that led to the decision. If none of the rules applies, ask the contributor to choose; do not guess.
4. Before reviewing or editing, read these instruction files from the selected target repository—either [`fivetran/community_connectors`](https://github.com/fivetran/community_connectors) or [`fivetran/connector_sdk`](https://github.com/fivetran/connector_sdk):
   - `.github/instructions/configuration-review.instructions.md`
   - `.github/instructions/python-review.instructions.md`
   - `.github/instructions/readme-markdown.instructions.md`
   If the contribution is in the selected repository, use its local files. Otherwise, ask the contributor for a checkout path for that repository.
5. If the selected target repository or its instruction checkout is unavailable, explain the missing item in plain language and offer to obtain it. For example: “I need a local checkout of the selected repository to apply its submission rules. May I clone the upstream repository, or would you prefer to fork it first?” Wait for approval before cloning, forking, authenticating, or changing remotes.
6. Confirm that the target is a connector/example directory containing `connector.py`. If it is not, stop and explain that this skill supports connector/example submissions only; do not apply it to documentation-only, tooling, or repository-maintenance changes.
7. Inspect the connector's changed files and its relevant files: `connector.py`, `README.md`, and dependency files, excluding configuration contents and raw configuration diffs. Discover configuration-like files by path only at this stage; defer reading their contents until the submission configuration has been selected and can be scanned locally without exposing values, as described below. Do not inspect or print real local configuration files such as `configuration_local.json`.

## Optional connector evaluation

Before making any edits, including non-behavioral compliance edits such as comments, README formatting, placeholders, or Black formatting, ask the contributor whether they want to run the host's `evaluate-connector` skill to identify performance bottlenecks and other quality improvements.

If they agree, invoke the evaluation skill and apply only changes the contributor authorizes. Then continue with this submission skill's review-and-fix workflow on the evaluated connector. If they decline, continue directly with the review-and-fix workflow.

## Review and fix workflow

Perform the following sequence. Treat BLOCKER and REQUEST_CHANGES levels from the loaded GitHub review instructions as such in the final report.

### Preserve and sanitize configuration

#### Select the submission configuration

1. Use `configuration.json` only when it is the single clear, tracked configuration file for the connector.
2. If multiple configuration-like JSON files exist under different names, list their paths only and ask the contributor which one is the tracked submission configuration. Do not read their values until the contributor identifies the file.
3. Never read or print a known local credential file such as `configuration_local.json`.

If `configuration.json` is missing, ask: “Do you have a sanitized tracked submission configuration at another path?” Then follow the contributor's answer:

- If they provide a safe path, use that file for the checks.
- If they confirm that no submission configuration exists and `connector.py` accesses configuration keys, create `configuration.json` with every statically identifiable key as a descriptive placeholder. For example, `configuration["api_key"]` becomes `"api_key": "<YOUR_API_KEY>"`.
- If they confirm that no submission configuration exists and `connector.py` does not access any configuration keys, create an empty `configuration.json`:

```json
{}
```

- If the contributor is unsure, or `connector.py` constructs configuration keys dynamically so their names cannot be determined, stop and ask before selecting or creating a file.

#### Scan without exposing values

When the contributor identifies the tracked submission configuration, or confirms that a new configuration file should be created, scan that file locally. The scan may read values to detect credentials, but it must not print, echo, paste, or return those values to chat, logs, command output, README content, or the PR. Report only safe information, such as the configuration key and the detected issue category.

Parse the file as JSON and check that it is a JSON object, uses descriptive consistent keys, and that every value is a descriptive string placeholder in the form `<DESCRIPTION_HERE>`.

Also scan it for credentials, tokens, passwords, personal data, embedded-credential URLs, database connection strings, IP addresses, internal host names, base64-looking values, and JWTs. Apply the exact security and completeness checks in the loaded configuration instruction, including agreement with connector code and README.

#### Sanitize confirmed secrets

If a real or possible credential, personal value, or any non-placeholder value is found, warn the contributor before modifying the file:

> `configuration.json` is about to be replaced with safe placeholders. Save the real values in a separate untracked local configuration file, such as `configuration_local.json`, before continuing. Do not commit that local file.

Ask for confirmation. Only after confirmation, replace tracked configuration values with specific angle-bracket placeholders that preserve each field's intended purpose. Re-parse and scan the resulting file without exposing values.

#### Configuration submission gate

Before submission, ensure that the tracked submission configuration file is named `configuration.json`. If the contributor selected a safe file with a different name, ask before renaming, copying, or replacing files.

Before submission, verify that every configuration value is a descriptive angle-bracket placeholder and that the file contains no credentials, tokens, passwords, personal data, embedded-credential URLs, connection strings, IP addresses, internal host names, base64-looking values, or JWTs.

### Apply the Python instructions

Review `connector.py` against the loaded Python instruction in full. This includes SDK v2 operation usage, validation, logging, imports and dependencies, schema and state handling, error handling, streaming/pagination, naming/constants, docstrings, and main block requirements.

For every `op.upsert()` and `op.checkpoint()` call, verify the immediately preceding comment block matches the required block in the loaded instruction. Add the required block when it is missing; do not invent abbreviated wording. Also preserve the instruction's required `update()` opening log statement and its main-block comments.

Make only unambiguous compliance edits. Before a change that affects connector behavior (for example, retry policy, pagination, state advancement, primary keys, or configuration validation), describe the issue and ask the contributor to approve the proposed fix. Do not claim a semantic check passed merely because it was not mechanically verifiable.

### Apply the README instructions

If `README.md` is missing, create it before reviewing the rest of the documentation. Derive the connector name, configuration keys, tables, incremental-sync behavior, dependencies, and other verifiable facts from the connector files. Ask the contributor for information that cannot be safely inferred, such as the connector overview, how credentials are obtained, API limitations, and feature claims. Do not invent product behavior, authentication steps, or external URLs.

Create the README in the structure required by the selected repository's README instruction: one Title Case H1; Sentence case lower-level headings; required sections in the prescribed order; and optional Configuration file, Requirements file, Authentication, and Pagination sections when they apply. Include the configuration keys as safe placeholders, not real values. Then review the generated README using the same instruction.

For an existing or generated README, enforce exactly one Title Case H1 and Sentence case for every lower-level heading; do not uppercase headings. Enforce the prescribed section requirements/order, configuration and dependency documentation, authentication/pagination requirements where applicable, list style, and formatting restrictions.

Apply these submission rules in both repositories:

- The Getting started section must include its required explanation and the correct initialization command for the submitted connector:
  - For a Community Connector, use its complete path relative to the Community Connectors repository root, with no `connectors/` prefix. For example, use `fivetran init --template github` for `github/`, or `fivetran init --template veeva_vault/basic_auth` for `veeva_vault/basic_auth/`.
  - For a Connector SDK example, use its complete path relative to the Connector SDK repository, including `examples/`. For example, use `fivetran init --template examples/quickstart/hello` or `fivetran init --template examples/common_patterns/authentication/api_key`.
  - Preserve an existing correct directory. Otherwise, derive it from the contribution's actual directory. If the directory does not map to one of these locations, ask the contributor rather than guessing.
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

If the repository does not provide a Flake8 wrapper script. Run Flake8 from the repository root so its `.flake8` configuration and per-file ignores apply, following the CI invocation:

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

If approved, create a concise PR title from the verified change. Use an action-oriented title that names the connector or SDK material affected; do not ask the contributor to write it unless the change cannot be identified from the files.

Fill the Description section with a brief, factual explanation of what the connector does and the data it syncs, based only on verified connector code and documentation. Do not frame it as a summary of implementation changes, include limitations, or add unverified claims. Then create a pull request with this body only:

```markdown
### Description

<brief explanation of what the connector does and the data it syncs>

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

