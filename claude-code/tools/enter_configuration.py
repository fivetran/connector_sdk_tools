#!/usr/bin/env python3
"""
Enter and encrypt configuration values for a Fivetran connector.

Run this script directly in your terminal to securely enter API credentials.
Values are encrypted before being saved to configuration.json.

Uses a local master secret file, creating it on first use.
"""
import base64
import getpass
import hashlib
import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()

ENCRYPTED_PREFIX = "ENCRYPTED:"
SECRET_FILE = Path.home() / ".fivetran" / "csdk_master_secret"


def get_fernet():
    try:
        from cryptography.fernet import Fernet, InvalidToken
    except ImportError:
        print("Error: Missing required dependencies.")
        print(f"\nInstall with:\n  pip install -r {SCRIPT_DIR}/requirements.txt")
        sys.exit(1)
    return Fernet, InvalidToken


def load_master_secret(create: bool) -> str:
    """Load the local master secret file, optionally creating it."""
    import secrets as secrets_module

    if SECRET_FILE.exists():
        master_secret = SECRET_FILE.read_text().strip()
        if master_secret:
            return master_secret

    if not create:
        print("Error: configuration.json is encrypted, but the local encryption secret is missing.")
        print(f"Expected local secret file: {SECRET_FILE}")
        print("Restore the matching local secret file, then run this script again.")
        sys.exit(1)

    master_secret = secrets_module.token_urlsafe(32)
    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        SECRET_FILE.parent.chmod(0o700)
    except OSError:
        pass

    fd = os.open(str(SECRET_FILE), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(master_secret + "\n")

    print("Created a local encryption secret.")
    print(f"Saved it to: {SECRET_FILE}")
    print("This script will use it now, and the test/deploy tools will use it later.")
    print("")
    return master_secret


def get_encryption_key(username: str = "local-user", create_secret: bool = True) -> bytes:
    """Derive encryption key from the local master secret."""
    master_secret = load_master_secret(create=create_secret)

    key = hashlib.pbkdf2_hmac(
        'sha256',
        master_secret.encode('utf-8'),
        username.encode('utf-8'),
        iterations=100000,
        dklen=32
    )
    return base64.urlsafe_b64encode(key)


def encrypt_config(config: dict) -> str:
    """Encrypt a configuration dictionary."""
    Fernet, _ = get_fernet()
    key = get_encryption_key()
    fernet = Fernet(key)
    json_bytes = json.dumps(config, indent=2).encode('utf-8')
    encrypted = fernet.encrypt(json_bytes)
    return ENCRYPTED_PREFIX + encrypted.decode('utf-8')


def decrypt_config(encrypted_content: str) -> dict:
    """Decrypt an encrypted configuration string."""
    Fernet, InvalidToken = get_fernet()
    key = get_encryption_key(create_secret=False)
    fernet = Fernet(key)

    if encrypted_content.startswith(ENCRYPTED_PREFIX):
        encrypted_content = encrypted_content[len(ENCRYPTED_PREFIX):]

    try:
        decrypted_bytes = fernet.decrypt(encrypted_content.encode('utf-8'))
    except InvalidToken:
        print("Error: configuration.json is encrypted, but this local secret cannot decrypt it.")
        print(f"Expected local secret file: {SECRET_FILE}")
        print("Run this script on the same machine/user profile that encrypted the file, or restore the matching local secret file.")
        sys.exit(1)

    return json.loads(decrypted_bytes.decode('utf-8'))


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

    content = config_path.read_text().strip()
    was_encrypted = content.startswith(ENCRYPTED_PREFIX)
    if was_encrypted:
        config = decrypt_config(content)
        print(f"{config_path} is already encrypted. Enter replacement values below.")
        print("Press Enter to keep an existing value.")
    else:
        try:
            config = json.loads(content)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in {config_path}: {e}")
            sys.exit(1)

    if not config:
        print("Error: No configuration fields found.")
        sys.exit(1)

    print(f"\nEnter values for {len(config)} field(s):\n")

    # Collect values for each field
    sensitive_keywords = ['key', 'token', 'secret', 'password', 'credential', 'auth']
    new_config = {}

    for field, current_value in config.items():
        is_sensitive = any(kw in field.lower() for kw in sensitive_keywords)

        if is_sensitive:
            keep_hint = " [press Enter to keep existing]" if was_encrypted and current_value else ""
            value = getpass.getpass(f"  {field}{keep_hint}: ")
            if was_encrypted and not value and current_value:
                value = current_value
        else:
            default_hint = f" [{current_value}]" if current_value else ""
            value = input(f"  {field}{default_hint}: ").strip()
            if not value and current_value:
                value = current_value

        new_config[field] = value

    # Encrypt and save
    try:
        encrypted = encrypt_config(new_config)
        config_path.write_text(encrypted)
        print(f"\nConfiguration encrypted and saved to {config_path}")
    except Exception as e:
        print(f"\nError: Failed to encrypt: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
