#!/usr/bin/env python3
"""
Deploy a connector to Fivetran.

Reads FIVETRAN_API_KEY from env, auto-discovers the destination via the
Fivetran REST API, then passes the encrypted configuration to `fivetran
deploy` via a named pipe (plaintext credentials never touch disk).

Usage:
    python deploy_connector.py <connector_directory>
"""
import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
API_BASE = "https://api.fivetran.com/v1"

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:
    print("Error: Missing required dependencies.")
    print(f"\nInstall with:\n  pip install -r {SCRIPT_DIR}/requirements.txt")
    sys.exit(1)


ENCRYPTED_PREFIX = "ENCRYPTED:"


def get_encryption_key(username: str = "local-user") -> bytes:
    """Derive encryption key from FIVETRAN_CSDK_MASTER_SECRET environment variable."""
    import secrets as secrets_module
    import platform

    master_secret = os.getenv("FIVETRAN_CSDK_MASTER_SECRET")
    if not master_secret:
        new_secret = secrets_module.token_urlsafe(32)
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
    key = get_encryption_key()
    fernet = Fernet(key)
    if encrypted_content.startswith(ENCRYPTED_PREFIX):
        encrypted_content = encrypted_content[len(ENCRYPTED_PREFIX):]
    decrypted_bytes = fernet.decrypt(encrypted_content.encode('utf-8'))
    return json.loads(decrypted_bytes.decode('utf-8'))


def load_api_key() -> str:
    key = os.getenv("FIVETRAN_API_KEY")
    if not key:
        print("Error: FIVETRAN_API_KEY environment variable is not set.")
        print("")
        print("To deploy, you need a Fivetran API key with CONNECTOR:READ permission.")
        print("Create one at: https://fivetran.com/dashboard/user/api-config")
        print("")
        print("Then add it to your shell config (e.g. ~/.zshrc):")
        print("  export FIVETRAN_API_KEY=...")
        print("")
        print("Reload your shell and re-run this command.")
        sys.exit(1)
    return key


def fivetran_get(path: str, api_key: str) -> dict:
    """GET a Fivetran REST API path and return the parsed JSON body."""
    url = f"{API_BASE}{path}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        print(f"Error: Fivetran API {path} returned {e.code}.")
        if e.code in (401, 403):
            print("Your FIVETRAN_API_KEY is missing or lacks required permissions.")
            print("Required: CONNECTOR:READ (and DESTINATION:READ for destination lookup).")
        if body:
            print(f"Response: {body[:500]}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Error: Could not reach Fivetran API ({e.reason}).")
        sys.exit(1)


def pick_one(items: list, label_fn, prompt: str, singular: str):
    """Auto-select if one item, prompt if multiple, exit if zero."""
    if not items:
        return None
    if len(items) == 1:
        item = items[0]
        print(f"Using {singular}: {label_fn(item)}")
        return item
    print(f"\n{prompt}")
    for i, item in enumerate(items, 1):
        print(f"  [{i}] {label_fn(item)}")
    while True:
        try:
            choice = input(f"Pick [1-{len(items)}]: ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(items):
                return items[idx]
        except (ValueError, EOFError):
            pass
        print("Invalid selection. Try again.")


def discover_destination(api_key: str) -> str:
    """Return a destination ID via Fivetran REST API, prompting if ambiguous."""
    groups_resp = fivetran_get("/groups?limit=1000", api_key)
    groups = groups_resp.get("data", {}).get("items", [])
    if not groups:
        print("Error: No groups found in your Fivetran account.")
        print("Create one at https://fivetran.com/dashboard and re-run.")
        sys.exit(1)

    group = pick_one(
        groups,
        label_fn=lambda g: f"{g.get('name')} ({g.get('id')})",
        prompt="Multiple groups found. Pick one:",
        singular="group",
    )

    dest_resp = fivetran_get(f"/groups/{group['id']}/destinations?limit=1000", api_key)
    destinations = dest_resp.get("data", {}).get("items", [])
    if not destinations:
        print(f"Error: No destinations in group '{group.get('name')}'.")
        print("Create one at: https://fivetran.com/dashboard/destinations")
        print("Then re-run this command.")
        sys.exit(1)

    destination = pick_one(
        destinations,
        label_fn=lambda d: f"{d.get('id')} ({d.get('service', '?')}, region {d.get('region', '?')})",
        prompt="Multiple destinations found. Pick one:",
        singular="destination",
    )
    return destination["id"]


class ConfigPipe:
    """Named pipe (FIFO) for securely passing config to the SDK."""
    def __init__(self, project_dir: Path, config: dict):
        self.config = config
        self.pipe_path = project_dir / ".config_pipe"
        self.writer_thread = None
        self.write_complete = None

    def __enter__(self):
        if self.pipe_path.exists():
            self.pipe_path.unlink()
        os.mkfifo(self.pipe_path, 0o600)
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
    parser = argparse.ArgumentParser(description="Deploy a connector to Fivetran")
    parser.add_argument("connector_directory", help="Path to the connector directory")
    args = parser.parse_args()

    connector_dir = Path(args.connector_directory).resolve()
    if not connector_dir.exists():
        print(f"Error: Directory not found: {connector_dir}")
        sys.exit(1)

    config_path = connector_dir / "configuration.json"
    if not config_path.exists():
        print(f"Error: configuration.json not found in {connector_dir}")
        sys.exit(1)

    content = config_path.read_text().strip()
    if not content.startswith(ENCRYPTED_PREFIX):
        print("Error: configuration.json is not encrypted.", file=sys.stderr)
        print("", file=sys.stderr)
        print("Credentials must be entered via the encryption script — never edited", file=sys.stderr)
        print("by hand or pasted in chat. Run, in a separate terminal:", file=sys.stderr)
        print("", file=sys.stderr)
        print(f"  python {SCRIPT_DIR}/enter_configuration.py {config_path}", file=sys.stderr)
        print("", file=sys.stderr)
        print("Then re-run this command.", file=sys.stderr)
        sys.exit(2)

    try:
        config = decrypt_config(content)
    except InvalidToken:
        print("Error: Failed to decrypt configuration.", file=sys.stderr)
        print("Make sure FIVETRAN_CSDK_MASTER_SECRET matches what was used to encrypt.", file=sys.stderr)
        sys.exit(1)

    api_key = load_api_key()
    destination_id = discover_destination(api_key)

    venv_activate = connector_dir / ".venv" / "bin" / "activate"

    with ConfigPipe(connector_dir, config) as pipe_path:
        cmd = f"cd {connector_dir} && "
        if venv_activate.exists():
            cmd += f"source {venv_activate} && "
        cmd += f"fivetran deploy --api-key {api_key} --destination {destination_id} --configuration {pipe_path}"

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
        for line in process.stdout:
            print(line, end='', flush=True)
        process.wait()
        sys.exit(process.returncode)


if __name__ == "__main__":
    main()
