#!/usr/bin/env python3
"""
Run a connector with encrypted configuration.

Decrypts configuration in memory and passes it to fivetran debug via named pipe.
Credentials never touch disk in plaintext.

Usage:
    python run_connector.py <connector_directory>
"""
import base64
import hashlib
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()

ENCRYPTED_PREFIX = "ENCRYPTED:"


class DecryptionFailed(Exception):
    """Raised when encrypted configuration cannot be decrypted."""


def get_fernet():
    try:
        from cryptography.fernet import Fernet, InvalidToken
    except ImportError:
        print("Error: Missing required dependencies.")
        print(f"\nInstall with:\n  pip install -r {SCRIPT_DIR}/requirements.txt")
        sys.exit(1)
    return Fernet, InvalidToken


def get_encryption_key(username: str = "local-user") -> bytes:
    """Derive encryption key from FIVETRAN_CSDK_MASTER_SECRET environment variable."""
    import secrets as secrets_module
    import platform

    master_secret = os.getenv("FIVETRAN_CSDK_MASTER_SECRET")
    if not master_secret:
        # Generate a new secret
        new_secret = secrets_module.token_urlsafe(32)

        # Detect shell config file
        shell = os.environ.get("SHELL", "")
        system = platform.system()
        if system == "Windows":
            config_file = "$PROFILE"
        elif "zsh" in shell:
            config_file = "~/.zshrc"
        elif "bash" in shell:
            config_file = "~/.bash_profile" if system == "Darwin" else "~/.bashrc"
        else:
            config_file = "~/.profile"

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


def decrypt_config(encrypted_content: str) -> dict:
    """Decrypt an encrypted configuration string."""
    Fernet, InvalidToken = get_fernet()
    key = get_encryption_key()
    fernet = Fernet(key)

    if encrypted_content.startswith(ENCRYPTED_PREFIX):
        encrypted_content = encrypted_content[len(ENCRYPTED_PREFIX):]

    try:
        decrypted_bytes = fernet.decrypt(encrypted_content.encode('utf-8'))
    except InvalidToken as exc:
        raise DecryptionFailed from exc
    return json.loads(decrypted_bytes.decode('utf-8'))


class ConfigPipe:
    """
    Named pipe (FIFO) for securely passing config to the SDK.
    Data never touches disk - stays in kernel buffer.
    """
    def __init__(self, project_dir: Path, config: dict):
        self.config = config
        self.pipe_path = project_dir / ".config_pipe"
        self.writer_thread = None
        self.write_complete = None

    def __enter__(self):
        # Remove any stale pipe
        if self.pipe_path.exists():
            self.pipe_path.unlink()

        # Create named pipe with restrictive permissions
        os.mkfifo(self.pipe_path, 0o600)

        # Event to signal when write is complete
        self.write_complete = threading.Event()

        def write_config():
            try:
                with open(self.pipe_path, 'w') as f:
                    json.dump(self.config, f)
            finally:
                self.write_complete.set()

        self.writer_thread = threading.Thread(target=write_config, daemon=True)
        self.writer_thread.start()

        return self.pipe_path

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.write_complete:
            self.write_complete.wait(timeout=30)
        try:
            if self.pipe_path.exists():
                self.pipe_path.unlink()
        except Exception:
            pass


def main():
    if len(sys.argv) < 2:
        print("Usage: python run_connector.py <connector_directory>")
        sys.exit(1)

    connector_dir = Path(sys.argv[1]).resolve()

    if not connector_dir.exists():
        print(f"Error: Directory not found: {connector_dir}")
        sys.exit(1)

    config_path = connector_dir / "configuration.json"
    if not config_path.exists():
        print(f"Error: configuration.json not found in {connector_dir}")
        sys.exit(1)

    content = config_path.read_text().strip()

    # Refuse to run with plaintext config — credentials must be encrypted at rest.
    if not content.startswith(ENCRYPTED_PREFIX):
        print("Error: configuration.json is not encrypted.", file=sys.stderr)
        print("", file=sys.stderr)
        print("Credentials must be entered via the encryption script — never edited", file=sys.stderr)
        print("by hand or pasted in chat. Run, in a separate terminal:", file=sys.stderr)
        print("", file=sys.stderr)
        print(f'  cd "{connector_dir}"', file=sys.stderr)
        print(f'  python "{SCRIPT_DIR}/enter_configuration.py" "configuration.json"', file=sys.stderr)
        print("", file=sys.stderr)
        print("Then re-run this command.", file=sys.stderr)
        sys.exit(2)

    try:
        config = decrypt_config(content)
    except DecryptionFailed:
        print("Error: Failed to decrypt configuration.", file=sys.stderr)
        print("Make sure FIVETRAN_CSDK_MASTER_SECRET matches what was used to encrypt.", file=sys.stderr)
        sys.exit(1)

    # Activate venv if present
    venv_activate = connector_dir / ".venv" / "bin" / "activate"

    # Run fivetran debug with config via named pipe
    with ConfigPipe(connector_dir, config) as pipe_path:
        cmd = f"cd {connector_dir} && "
        if venv_activate.exists():
            cmd += f"source {venv_activate} && "
        cmd += f"fivetran debug --configuration {pipe_path}"

        # Stream output in real-time
        process = subprocess.Popen(
            cmd,
            shell=True,
            executable="/bin/bash",
            cwd=connector_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            universal_newlines=True
        )

        # Print output as it arrives, with timeout handled in Python
        import signal

        def timeout_handler(signum, frame):
            process.kill()
            print("\nError: Command timed out after 60 seconds")
            sys.exit(124)

        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(60)

        try:
            for line in process.stdout:
                print(line, end='', flush=True)
            process.wait()
        finally:
            signal.alarm(0)  # Cancel the alarm

        sys.exit(process.returncode)


if __name__ == "__main__":
    main()
