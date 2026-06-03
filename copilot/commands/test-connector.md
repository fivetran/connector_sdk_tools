---
description: Test an existing Fivetran connector locally
---

Invoke the `test-connector` skill from this plugin to test the user's connector locally and surface any errors or warnings.

Credential handling is not interactive. Do not ask how the user wants to provide credentials. Do not use choice menus or multi-option UIs for credentials. The test flow must run `tools/run_connector.py`; if it reports that `configuration.json` is not encrypted, tell the user to run `tools/enter_configuration.py` in a separate terminal and stop. Do not run `tools/enter_configuration.py` yourself.
