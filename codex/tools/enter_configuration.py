#!/usr/bin/env python3
"""
Enter and encrypt configuration values for a Fivetran connector.

Run this script directly in your terminal to securely enter API credentials.
Configuration field values are encrypted before being saved to configuration.json.
Runtime tools also allow user-chosen plaintext values.

Uses a local master secret file, creating it on first use.
"""
import getpass
import json
import os
import secrets
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()

ENCRYPTED_PREFIX = "ENCRYPTED:"
ENCRYPTED_TOKEN_VERSION = "v1"
ENCRYPTED_TOKEN_ALGORITHM = "local-fernet"
SECRET_FILE = Path.home() / ".fivetran" / "csdk_master_secret"
FERNET_KEY_PREFIX = "FERNET_KEY:"


class MissingMasterSecret(Exception):
    """Raised when encrypted values exist but the local secret is missing."""


class DecryptionFailed(Exception):
    """Raised when encrypted values cannot be decrypted."""


def get_fernet():
    try:
        from cryptography.fernet import Fernet, InvalidToken
    except ImportError:
        print("Error: Missing required dependencies.")
        print(f"\nInstall with:\n  pip install -r {SCRIPT_DIR}/requirements.txt")
        sys.exit(1)
    return Fernet, InvalidToken


def create_master_secret(replacing_existing: bool = False) -> str:
    """Create a local Fernet key file with owner-only permissions."""
    Fernet, _ = get_fernet()
    key_id = secrets.token_urlsafe(8)
    master_secret = f"{FERNET_KEY_PREFIX}{ENCRYPTED_TOKEN_VERSION}:{key_id}:{Fernet.generate_key().decode('utf-8')}"
    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        SECRET_FILE.parent.chmod(0o700)
    except OSError:
        pass

    if replacing_existing:
        SECRET_FILE.write_text(master_secret + "\n")
        try:
            SECRET_FILE.chmod(0o600)
        except OSError:
            pass
        print("Replaced an unsupported local encryption secret format.")
    else:
        fd = os.open(str(SECRET_FILE), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(master_secret + "\n")
        print("Created a local encryption secret.")

    print(f"Saved it to: {SECRET_FILE}")
    print("This script will use it now, and the test/deploy tools will use it later.")
    print("")
    return master_secret


def load_master_secret(create: bool) -> str:
    """Load the local master secret file, optionally creating it."""
    if SECRET_FILE.exists():
        try:
            SECRET_FILE.parent.chmod(0o700)
            SECRET_FILE.chmod(0o600)
        except OSError:
            pass
        master_secret = SECRET_FILE.read_text().strip()
        if parse_master_secret(master_secret):
            return master_secret
        if create:
            return create_master_secret(replacing_existing=True)

    if not create:
        raise MissingMasterSecret

    return create_master_secret()


def parse_master_secret(master_secret: str) -> tuple[str, bytes] | None:
    """Return key metadata from a supported local secret file."""
    if not master_secret.startswith(FERNET_KEY_PREFIX):
        return None
    parts = master_secret[len(FERNET_KEY_PREFIX):].split(":", 2)
    if len(parts) != 3:
        return None
    version, key_id, key = parts
    if version != ENCRYPTED_TOKEN_VERSION or not key_id or not key:
        return None
    return key_id, key.encode("utf-8")


def get_encryption_key(create_secret: bool = True) -> tuple[str, bytes]:
    """Return the local Fernet key id and key."""
    master_secret = load_master_secret(create=create_secret)
    parsed = parse_master_secret(master_secret)
    if parsed is None:
        raise MissingMasterSecret
    return parsed


def is_sensitive_field(field: str) -> bool:
    """Return whether a configuration field should be protected at rest."""
    return True


def encrypt_value(value: str) -> str:
    """Encrypt a single sensitive field value."""
    Fernet, _ = get_fernet()
    key_id, key = get_encryption_key()
    try:
        fernet = Fernet(key)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("local encryption key is invalid") from exc

    encrypted = fernet.encrypt(value.encode('utf-8'))
    return f"{ENCRYPTED_PREFIX}{ENCRYPTED_TOKEN_VERSION}:{key_id}:{ENCRYPTED_TOKEN_ALGORITHM}:{encrypted.decode('utf-8')}"


def decrypt_value(encrypted_content: str) -> str:
    """Decrypt a single encrypted sensitive field value."""
    Fernet, InvalidToken = get_fernet()
    local_key_id, key = get_encryption_key(create_secret=False)
    try:
        fernet = Fernet(key)
    except (TypeError, ValueError) as exc:
        raise DecryptionFailed from exc

    if not encrypted_content.startswith(ENCRYPTED_PREFIX):
        raise DecryptionFailed
    parts = encrypted_content[len(ENCRYPTED_PREFIX):].split(":", 3)
    if len(parts) != 4:
        raise DecryptionFailed
    version, key_id, algorithm, token = parts
    if version != ENCRYPTED_TOKEN_VERSION or key_id != local_key_id or algorithm != ENCRYPTED_TOKEN_ALGORITHM:
        raise DecryptionFailed

    try:
        decrypted_bytes = fernet.decrypt(token.encode('utf-8'))
        return decrypted_bytes.decode('utf-8')
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise DecryptionFailed from exc


def load_configuration(config_path: Path) -> tuple[dict, bool, bool]:
    """
    Return current values for prompting, whether encrypted values exist,
    and whether existing values can be kept.
    """
    content = config_path.read_text().strip()

    try:
        raw_config = json.loads(content)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {config_path}: {e}")
        sys.exit(1)

    if not isinstance(raw_config, dict):
        print(f"Error: {config_path} must contain a JSON object.")
        sys.exit(1)

    config = {}
    had_encrypted_values = False
    can_keep_existing = False

    for field, value in raw_config.items():
        if is_sensitive_field(field) and isinstance(value, str) and value.startswith(ENCRYPTED_PREFIX):
            had_encrypted_values = True
            try:
                config[field] = decrypt_value(value)
                can_keep_existing = True
            except (MissingMasterSecret, DecryptionFailed):
                print("")
                print(f"Could not decrypt the existing encrypted value for {field!r}.")
                print("Prompting for a replacement value.")
                print("")
                config[field] = ""
        else:
            config[field] = value
            if is_sensitive_field(field) and value:
                can_keep_existing = True

    return config, had_encrypted_values, can_keep_existing


def protect_config_values(config: dict) -> dict:
    """Return a JSON-ready config with all field values encrypted."""
    output_config = {}
    for field, value in config.items():
        string_value = value if isinstance(value, str) else str(value)
        if is_sensitive_field(field):
            output_config[field] = encrypt_value(string_value)
        else:
            output_config[field] = string_value
    return output_config


def main():
    if not sys.stdin.isatty():
        print("Error: enter_configuration.py must be run in a real terminal.")
        print("")
        print("Open a separate terminal and run this command there.")
        print("Do not run this script from an AI chat tool or non-interactive shell.")
        sys.exit(2)

    print("\n=== Fivetran Connector Configuration ===\n")

    # Determine config file path
    if len(sys.argv) > 1:
        config_path = Path(sys.argv[1])
    else:
        config_path = Path("configuration.json")

    if not config_path.exists():
        print(f"Error: {config_path} not found.")
        print("Make sure you're in a connector directory with a configuration.json file.")
        sys.exit(1)

    config, had_encrypted_values, can_keep_existing = load_configuration(config_path)
    if had_encrypted_values:
        print(f"{config_path} already has encrypted values. Enter replacement values below.")
        if can_keep_existing:
            print("Press Enter to keep an existing value.")

    if not config:
        print("Error: No configuration fields found.")
        sys.exit(1)

    print(f"\nEnter values for {len(config)} field(s):\n")

    new_config = {}

    for field, current_value in config.items():
        if is_sensitive_field(field):
            keep_hint = " [press Enter to keep existing]" if can_keep_existing and current_value else ""
            value = getpass.getpass(f"  {field}{keep_hint}: ")
            if can_keep_existing and not value and current_value:
                value = current_value
        else:
            default_hint = f" [{current_value}]" if current_value else ""
            value = input(f"  {field}{default_hint}: ").strip()
            if not value and current_value:
                value = current_value

        new_config[field] = value

    try:
        output_config = protect_config_values(new_config)
        config_path.write_text(json.dumps(output_config, indent=2) + "\n")
        print(f"\nConfiguration values encrypted and saved to {config_path}")
    except Exception as e:
        print(f"\nError: Failed to encrypt: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
