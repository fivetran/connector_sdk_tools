# TODO

## OS-backed configuration encryption

- Replace the current `cryptography`/Fernet-based local secret file implementation with OS-backed protection so users do not need to install Python crypto dependencies.
- Protect every `configuration.json` field value until typed configuration fields are available.
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
  - Plaintext values do not appear in logs, subprocess args, temp files, or persisted state.
- Remove `cryptography` from `tools/requirements.txt` and update README/setup instructions once all supported platforms have an OS-backed path.
