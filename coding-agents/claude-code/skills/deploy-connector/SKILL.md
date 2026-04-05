---
description: Package and deploy a Fivetran connector. Use when the user wants to deploy, package, or ship their connector.
---

> **Context**: This plugin is for the Fivetran Connector SDK (CSDK). "CSDK" is shorthand for "Connector SDK".

# Deploy Fivetran Connector

Package and deploy the connector in the current directory.

## Step 1: Pre-Deployment Validation

Verify the connector is ready for deployment:

1. **Files exist**: `connector.py`, `configuration.json`, `requirements.txt`, `README.md`
2. **Code quality**: Read `connector.py` and check for:
   - Both `schema()` and `update()` functions present
   - `connector = Connector(update=update, schema=schema)` in global scope
   - `if __name__ == "__main__": connector.debug()` entry point
   - No forbidden patterns (`log.error()`, `Dict[str, Any]`, `Generator`)
3. **Configuration**: `configuration.json` is valid JSON with string-only values

## Step 2: Run Final Test

Run the connector test using the secure runner:

```bash
python /path/to/coding-agent-plugins/claude-code/tools/run_connector.py <connector_directory>
```

If the test fails, classify the error (INFRA/FIRST_RUN/CODE) and offer to fix if it's a CODE error.

## Step 3: Deploy

Use the secure deploy tool which handles encrypted configs:

```bash
python /path/to/coding-agent-plugins/claude-code/tools/deploy_connector.py <connector_directory> --api-key <FIVETRAN_API_KEY> --destination <DESTINATION_ID>
```

If the user hasn't provided deployment credentials, explain what they need:
- A Fivetran API key (from Fivetran dashboard > Settings > API Config)
- A destination ID (from the Fivetran dashboard)

Refer to the Fivetran Connector SDK deployment docs:
https://fivetran.com/docs/connector-sdk/working-with-connector-sdk#deploytheconnector

## Alternative: Manual Packaging

If the user prefers manual deployment:

1. Create a ZIP file containing:
   - `connector.py`
   - `configuration.json`
   - `requirements.txt`
   - `README.md`
   - Any additional Python modules

2. Upload via the Fivetran dashboard

```bash
zip -r connector-package.zip connector.py configuration.json requirements.txt README.md
```
