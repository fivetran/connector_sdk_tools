# TODO

## OS-backed local configuration protection

- Replace the current `cryptography`/Fernet-based local secret file implementation with OS-backed protection so users do not need to install Python crypto dependencies.
- Keep the scope limited to local-at-rest protection for AI-assisted development. These tools decrypt values locally before `fivetran debug` / `fivetran deploy`; encrypted local values are not uploaded by the wrapper.
- Keep default encryption for every `configuration.json` field until typed configuration fields are available, while continuing to allow user-chosen plaintext values to pass through unchanged.
- Preserve inline metadata on encrypted values, using a provider-aware format such as:
  - `SECRET:v1:windows-dpapi:<key_id>:<payload>`
  - `SECRET:v1:macos-keychain:<key_id>:<payload>`
  - `SECRET:v1:linux-secret-service:<key_id>:<payload>`
- Implement providers:
  - Windows: DPAPI via stdlib `ctypes` calling `CryptProtectData` / `CryptUnprotectData`.
  - macOS: Keychain via stdlib `ctypes` and Security.framework. Avoid passing secrets through the `security` CLI argv.
  - Linux: Secret Service integration. Decide whether requiring `secret-tool` / libsecret is acceptable, or whether to implement D-Bus calls directly.
- Add tests that verify:
  - Encrypted config values are decrypted by run/deploy.
  - User-chosen plaintext config values pass through unchanged.
  - Encrypted values include version/provider/key metadata.
  - Unsupported providers or versions fail closed.
  - Values decrypted from encrypted tokens do not appear in logs, subprocess args, temp files, or persisted state.
- Treat key rotation as low priority for this local-only threat model. A simple recovery path is acceptable: delete/recreate the local protection secret and rerun `enter_configuration.py`.
- Remove `cryptography` from `tools/requirements.txt` and update README/setup instructions once all supported platforms have an OS-backed path.
