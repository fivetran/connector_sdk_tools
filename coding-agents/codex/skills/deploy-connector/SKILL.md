---
name: deploy-connector
description: Package and deploy a Fivetran connector to Fivetran. Use when the user wants to deploy or ship their connector.
---

# Deploy Fivetran Connector

**FIRST**: Read `sdk-reference.md` from the plugin directory to load SDK rules and patterns.

Package and deploy the connector in the current directory.

## Step 1: Pre-Deployment Validation

Verify the connector is ready:

1. **Files exist**: `connector.py`, `configuration.json`, `requirements.txt`, `README.md`
2. **Code quality**: Read `connector.py` and check for:
   - Both `schema()` and `update()` functions present
   - `connector = Connector(update=update, schema=schema)` in global scope
   - `if __name__ == "__main__": connector.debug()` entry point
   - No forbidden patterns (`log.error()`, `Dict[str, Any]`, `Generator`)
3. **Configuration**: `configuration.json` is valid JSON with string-only values

## Step 2: Run Final Test

Use the secure runner:

```bash
python <plugin_dir>/tools/run_connector.py <connector_directory>
```

If the test fails, classify the error (INFRA/FIRST_RUN/CODE) and invoke `$fix_connector` if it's a CODE error.

## Step 3: Deploy

Use the secure deploy tool which handles encrypted configs:

```bash
python <plugin_dir>/tools/deploy_connector.py <connector_directory> --api-key <FIVETRAN_API_KEY> --destination <DESTINATION_ID>
```

If the user hasn't provided deployment credentials, explain what they need:
- A Fivetran API key (from Fivetran dashboard > Settings > API Config)
- A destination ID (from the Fivetran dashboard)

Reference: https://fivetran.com/docs/connector-sdk/working-with-connector-sdk#deploytheconnector

## Alternative: Manual Packaging

If the user prefers manual deployment:

1. Create a ZIP file:
   ```bash
   zip -r connector-package.zip connector.py configuration.json requirements.txt README.md
   ```
2. Upload via the Fivetran dashboard
