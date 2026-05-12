#!/usr/bin/env python3
"""
Enter and encrypt configuration values for a Fivetran connector.

Run this script directly in your terminal to securely enter API credentials.
Values are encrypted before being saved to configuration.json.

Requires FIVETRAN_CSDK_MASTER_SECRET environment variable to be set.
"""
import base64
import getpass
import hashlib
import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()

try:
    from cryptography.fernet import Fernet
except ImportError:
    print("Error: Missing required dependencies.")
    print(f"\nInstall with:\n  pip install -r {SCRIPT_DIR}/requirements.txt")
    sys.exit(1)


ENCRYPTED_PREFIX = "ENCRYPTED:"


def get_shell_config_file() -> str:
    """Detect the user's shell and return the appropriate config file."""
    import platform
    shell = os.environ.get("SHELL", "")
    system = platform.system()

    if system == "Windows":
        return "$PROFILE"  # PowerShell profile
    elif "zsh" in shell:
        return "~/.zshrc"
    elif "bash" in shell:
        if system == "Darwin":
            return "~/.bash_profile"
        return "~/.bashrc"
    else:
        return "~/.profile"


def get_encryption_key(username: str = "local-user") -> bytes:
    """Derive encryption key from FIVETRAN_CSDK_MASTER_SECRET environment variable."""
    import secrets as secrets_module
    import platform

    master_secret = os.getenv("FIVETRAN_CSDK_MASTER_SECRET")
    if not master_secret:
        # Generate a new secret
        new_secret = secrets_module.token_urlsafe(32)
        config_file = get_shell_config_file()
        system = platform.system()

        print("Error: FIVETRAN_CSDK_MASTER_SECRET environment variable is not set.")
        print("\nAdd this line to your shell config file:")
        print(f"\n  # {config_file}")

        if system == "Windows":
            print(f'  $env:FIVETRAN_CSDK_MASTER_SECRET = "{new_secret}"')
        else:
            print(f'  export FIVETRAN_CSDK_MASTER_SECRET="{new_secret}"')

        print(f"\nThen reload your shell or run:")
        if system == "Windows":
            print(f"  . $PROFILE")
        else:
            print(f"  source {config_file}")

        sys.exit(1)

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
    key = get_encryption_key()
    fernet = Fernet(key)
    json_bytes = json.dumps(config, indent=2).encode('utf-8')
    encrypted = fernet.encrypt(json_bytes)
    return ENCRYPTED_PREFIX + encrypted.decode('utf-8')


def main():
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

    # Check if already encrypted
    content = config_path.read_text().strip()
    if content.startswith(ENCRYPTED_PREFIX):
        print(f"{config_path} is already encrypted.")
        response = input("Re-encrypt with new values? [y/N]: ").strip().lower()
        if response != 'y':
            print("Cancelled.")
            sys.exit(0)

        fields_str = input("Enter field names (comma-separated) [access_token]: ").strip()
        if not fields_str:
            fields_str = "access_token"
        fields = [f.strip() for f in fields_str.split(',') if f.strip()]
        config = {field: "" for field in fields}
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
            value = getpass.getpass(f"  {field}: ")
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
