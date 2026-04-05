"""
Encryption utilities for securing configuration files.

Uses derived per-user keys from a master secret for encryption at rest.
This prevents AI agents from reading credential values even if they access the file.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken


# Prefix to identify encrypted content
ENCRYPTED_PREFIX = "ENCRYPTED:"

# Master secret from environment (required for encryption features)
_master_secret: Optional[str] = None


def _get_master_secret() -> str:
    """Get the master secret from environment, with caching."""
    global _master_secret
    if _master_secret is None:
        _master_secret = os.getenv("CSDKAI_MASTER_SECRET")
        if not _master_secret:
            raise ValueError(
                "CSDKAI_MASTER_SECRET environment variable is required for encryption. "
                "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
            )
    return _master_secret


def get_user_encryption_key(username: str) -> bytes:
    """
    Derive a unique encryption key for a user from the master secret.

    Uses PBKDF2 with the username as salt to ensure each user has a unique key.
    The same username always produces the same key (deterministic).

    Args:
        username: The username to derive the key for

    Returns:
        A 32-byte key suitable for Fernet encryption (base64 URL-safe encoded)
    """
    master_secret = _get_master_secret()

    # Derive key using PBKDF2
    # - SHA256 hash function
    # - Username as salt (ensures per-user uniqueness)
    # - 100,000 iterations (industry standard for PBKDF2)
    # - 32 bytes output (256 bits, required for Fernet)
    key = hashlib.pbkdf2_hmac(
        'sha256',
        master_secret.encode('utf-8'),
        username.encode('utf-8'),
        iterations=100000,
        dklen=32
    )

    # Fernet requires base64 URL-safe encoding
    return base64.urlsafe_b64encode(key)


def encrypt_config(username: str, config: dict) -> str:
    """
    Encrypt a configuration dictionary for a specific user.

    Args:
        username: The username (used to derive encryption key)
        config: The configuration dictionary to encrypt

    Returns:
        Encrypted string with ENCRYPTED: prefix
    """
    key = get_user_encryption_key(username)
    fernet = Fernet(key)

    # Convert config to JSON bytes
    json_bytes = json.dumps(config, indent=2).encode('utf-8')

    # Encrypt
    encrypted = fernet.encrypt(json_bytes)

    # Return with prefix for easy identification
    return ENCRYPTED_PREFIX + encrypted.decode('utf-8')


def decrypt_config(username: str, encrypted_content: str) -> dict:
    """
    Decrypt an encrypted configuration string for a specific user.

    Args:
        username: The username (used to derive encryption key)
        encrypted_content: The encrypted string (with or without ENCRYPTED: prefix)

    Returns:
        Decrypted configuration dictionary

    Raises:
        InvalidToken: If decryption fails (wrong key or corrupted data)
        json.JSONDecodeError: If decrypted content is not valid JSON
    """
    key = get_user_encryption_key(username)
    fernet = Fernet(key)

    # Remove prefix if present
    if encrypted_content.startswith(ENCRYPTED_PREFIX):
        encrypted_content = encrypted_content[len(ENCRYPTED_PREFIX):]

    # Decrypt
    decrypted_bytes = fernet.decrypt(encrypted_content.encode('utf-8'))

    # Parse JSON
    return json.loads(decrypted_bytes.decode('utf-8'))


def is_encrypted(content: str) -> bool:
    """Check if content is encrypted (has ENCRYPTED: prefix)."""
    return isinstance(content, str) and content.startswith(ENCRYPTED_PREFIX)


def encrypt_single_value(username: str, value: str) -> str:
    """
    Encrypt a single string value for a specific user.

    Args:
        username: The username (used to derive encryption key)
        value: The string value to encrypt

    Returns:
        Encrypted string with ENCRYPTED: prefix
    """
    if not value:
        return value

    key = get_user_encryption_key(username)
    fernet = Fernet(key)

    # Encrypt the value
    encrypted = fernet.encrypt(value.encode('utf-8'))

    # Return with prefix for easy identification
    return ENCRYPTED_PREFIX + encrypted.decode('utf-8')


def decrypt_single_value(username: str, encrypted_value: str) -> str:
    """
    Decrypt a single encrypted value for a specific user.

    Args:
        username: The username (used to derive encryption key)
        encrypted_value: The encrypted string (with or without ENCRYPTED: prefix)

    Returns:
        Decrypted string value

    Raises:
        InvalidToken: If decryption fails (wrong key or corrupted data)
    """
    if not encrypted_value:
        return encrypted_value

    # If not encrypted, return as-is
    if not is_encrypted(encrypted_value):
        return encrypted_value

    key = get_user_encryption_key(username)
    fernet = Fernet(key)

    # Remove prefix
    encrypted_data = encrypted_value[len(ENCRYPTED_PREFIX):]

    # Decrypt
    decrypted_bytes = fernet.decrypt(encrypted_data.encode('utf-8'))

    return decrypted_bytes.decode('utf-8')


def load_config(path: Path, username: str) -> dict:
    """
    Load configuration from file, decrypting if necessary.

    Args:
        path: Path to the configuration file
        username: The username (for decryption key derivation)

    Returns:
        Configuration dictionary (decrypted if it was encrypted)
    """
    content = path.read_text()

    if is_encrypted(content):
        return decrypt_config(username, content)
    else:
        # Plain JSON (template not yet populated with secrets)
        return json.loads(content)


def save_config_encrypted(path: Path, username: str, config: dict) -> None:
    """
    Encrypt and save configuration to file.

    Args:
        path: Path to save the configuration file
        username: The username (for encryption key derivation)
        config: The configuration dictionary to encrypt and save
    """
    encrypted = encrypt_config(username, config)
    path.write_text(encrypted)


def save_config_plaintext(path: Path, config: dict) -> None:
    """
    Save configuration as plaintext JSON (for AI-generated templates).

    Args:
        path: Path to save the configuration file
        config: The configuration dictionary to save
    """
    path.write_text(json.dumps(config, indent=2))


# Utility function to check if encryption is available
def is_encryption_configured() -> bool:
    """Check if encryption is properly configured (master secret is set)."""
    try:
        _get_master_secret()
        return True
    except ValueError:
        return False
