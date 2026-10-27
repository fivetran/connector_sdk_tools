---
description: Prepare a Fivetran Connector SDK contribution for a pull request
argument-hint: "Connector directory name or path (e.g., 'github_connector' or './github_connector')"
---

Invoke the `connector-sdk-submit` skill from this plugin to submit a Connector SDK example or connector contribution in a pull request. The skill selects the appropriate upstream repository, applies its GitHub review instructions, sanitizes tracked configuration values, validates documentation, formats and lints code, and guides the contributor through the pull-request handoff.

User request: $ARGUMENTS
