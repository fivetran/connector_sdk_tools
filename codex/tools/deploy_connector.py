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
import re
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
import uuid
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
API_BASE = "https://api.fivetran.com/v1"

ENCRYPTED_PREFIX = "ENCRYPTED:"
ENCRYPTED_FIELD = "encrypted"
SECRET_FILE = Path.home() / ".fivetran" / "csdk_master_secret"


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


def load_master_secret() -> str:
    """Load the local master secret file."""
    if SECRET_FILE.exists():
        master_secret = SECRET_FILE.read_text().strip()
        if master_secret:
            return master_secret

    print("No local encryption secret found.", file=sys.stderr)
    print("", file=sys.stderr)
    print("Run enter_configuration.py in a separate terminal first. It will", file=sys.stderr)
    print(f"create {SECRET_FILE} and encrypt configuration.json.", file=sys.stderr)
    sys.exit(1)


def get_encryption_key(username: str = "local-user") -> bytes:
    """Derive encryption key from the local master secret."""
    master_secret = load_master_secret()

    key = hashlib.pbkdf2_hmac(
        'sha256',
        master_secret.encode('utf-8'),
        username.encode('utf-8'),
        iterations=100000,
        dklen=32
    )
    return base64.urlsafe_b64encode(key)


def decrypt_config(encrypted_content: str) -> dict:
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


def load_encrypted_config_content(config_path: Path) -> str | None:
    content = config_path.read_text().strip()
    if content.startswith(ENCRYPTED_PREFIX):
        return content

    try:
        config = json.loads(content)
    except json.JSONDecodeError:
        return None

    if not isinstance(config, dict):
        return None

    encrypted_content = config.get(ENCRYPTED_FIELD)
    if isinstance(encrypted_content, str) and encrypted_content.startswith(ENCRYPTED_PREFIX):
        return encrypted_content

    return None


def load_api_key() -> str:
    key = os.getenv("FIVETRAN_API_KEY")
    if not key:
        print("Error: FIVETRAN_API_KEY environment variable is not set.")
        print("")
        print("To deploy, you need a base64-encoded Fivetran API key ('{key}:{secret}')")
        print("with permission to manage connections and read destinations.")
        print("Create one at: https://fivetran.com/dashboard/user/api-config")
        print("")
        print("Then add it to your shell config (e.g. ~/.zshrc):")
        print("  export FIVETRAN_API_KEY=...")
        print("")
        print("Reload your shell and re-run this command.")
        sys.exit(1)
    return key


def fivetran_request(method: str, path: str, api_key: str, body: dict | None = None) -> dict:
    """Call a Fivetran REST API path and return the parsed JSON body.

    The Fivetran REST API uses HTTP Basic auth. FIVETRAN_API_KEY is the
    base64-encoded "{key}:{secret}" string — exactly the Basic-auth credential —
    so it is sent as `Authorization: Basic <key>` (the same value passed to
    `fivetran deploy --api-key`).
    """
    url = f"{API_BASE}{path}"
    headers = {
        "Authorization": f"Basic {api_key}",
        "Accept": "application/json",
    }
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, headers=headers, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        print(f"Error: Fivetran API {method} {path} returned {e.code}.")
        if e.code in (401, 403):
            print("Your FIVETRAN_API_KEY is missing or lacks required permissions.")
            print("It must be the base64-encoded '{key}:{secret}' string.")
        if err_body:
            print(f"Response: {err_body[:500]}")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Error: Could not reach Fivetran API ({e.reason}).")
        sys.exit(1)


def fivetran_get(path: str, api_key: str) -> dict:
    """GET a Fivetran REST API path and return the parsed JSON body."""
    return fivetran_request("GET", path, api_key)


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


def discover_destination_name(api_key: str) -> str:
    """Return the destination (group) NAME for `fivetran deploy --destination`.

    In Fivetran, a group and its destination share an identity; the value
    `fivetran deploy --destination` expects is the destination name shown on the
    dashboard, which is the group name (the CLI documents it as "aka 'group name'").
    """
    groups_resp = fivetran_get("/groups?limit=1000", api_key)
    groups = groups_resp.get("data", {}).get("items", [])
    if not groups:
        print("Error: No destinations found in your Fivetran account.")
        print("Create one at https://fivetran.com/dashboard/destinations and re-run.")
        sys.exit(1)

    group = pick_one(
        groups,
        label_fn=lambda g: f"{g.get('name')} ({g.get('id')})",
        prompt="Multiple destinations found. Pick one:",
        singular="destination",
    )
    return group["name"]


def sanitize_connection_name(raw: str) -> str:
    """Coerce a string into a valid Fivetran connection name.

    Rules: begins with `_` or a lowercase letter; only `_`, lowercase letters,
    or digits afterward.
    """
    name = "".join(ch if (ch.islower() or ch.isdigit() or ch == "_") else "_"
                    for ch in raw.lower())
    name = name.strip("_") or "connector"
    if not (name[0].islower() or name[0] == "_"):
        name = f"_{name}"
    return name


def unpause_connection(api_key: str, connection_id: str):
    """Unpause a connection so Fivetran begins syncing (consumes MAR)."""
    fivetran_request(
        "PATCH",
        f"/connections/{connection_id}",
        api_key,
        body={"paused": False},
    )
    print(f"Connection {connection_id} unpaused — the initial sync will begin.")
    print(f"Dashboard: https://fivetran.com/dashboard/connections/{connection_id}/status")


class ConfigPipe:
    """Named pipe for securely passing config to the SDK."""
    def __init__(self, project_dir: Path, config: dict):
        self.config = config
        self.project_dir = project_dir
        self.pipe_path = None
        self.writer_thread = None
        self.write_complete = None
        self.writer_error = None
        self._windows_handle = None

    def __enter__(self):
        if os.name == "nt":
            return self._enter_windows()
        return self._enter_posix()

    def _enter_posix(self):
        self.pipe_path = self.project_dir / ".config_pipe"
        if self.pipe_path.exists():
            self.pipe_path.unlink()
        os.mkfifo(self.pipe_path, 0o600)
        self.write_complete = threading.Event()

        def write_config():
            try:
                with open(self.pipe_path, 'w') as f:
                    json.dump(self.config, f)
            except Exception as exc:
                self.writer_error = exc
            finally:
                self.write_complete.set()

        self.writer_thread = threading.Thread(target=write_config, daemon=True)
        self.writer_thread.start()
        return self.pipe_path

    def _enter_windows(self):
        import ctypes
        from ctypes import wintypes

        pipe_name = rf"\\.\pipe\fivetran_config_{uuid.uuid4().hex}"
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        kernel32.CreateNamedPipeW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
        ]
        kernel32.CreateNamedPipeW.restype = wintypes.HANDLE
        kernel32.ConnectNamedPipe.argtypes = [wintypes.HANDLE, wintypes.LPVOID]
        kernel32.ConnectNamedPipe.restype = wintypes.BOOL
        kernel32.WriteFile.argtypes = [
            wintypes.HANDLE,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            wintypes.LPVOID,
        ]
        kernel32.WriteFile.restype = wintypes.BOOL
        kernel32.FlushFileBuffers.argtypes = [wintypes.HANDLE]
        kernel32.DisconnectNamedPipe.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

        pipe_access_outbound = 0x00000002
        pipe_type_byte = 0x00000000
        pipe_wait = 0x00000000
        error_pipe_connected = 535
        invalid_handle_value = wintypes.HANDLE(-1).value

        handle = kernel32.CreateNamedPipeW(
            pipe_name,
            pipe_access_outbound,
            pipe_type_byte | pipe_wait,
            1,
            65536,
            65536,
            0,
            None,
        )
        if handle == invalid_handle_value:
            raise OSError(ctypes.get_last_error(), "CreateNamedPipeW failed")

        self._windows_handle = handle
        self.write_complete = threading.Event()

        def write_config():
            try:
                connected = kernel32.ConnectNamedPipe(handle, None)
                if not connected:
                    err = ctypes.get_last_error()
                    if err != error_pipe_connected:
                        raise OSError(err, "ConnectNamedPipe failed")

                data = json.dumps(self.config).encode("utf-8")
                buffer = ctypes.create_string_buffer(data)
                written = wintypes.DWORD(0)
                ok = kernel32.WriteFile(
                    handle,
                    buffer,
                    len(data),
                    ctypes.byref(written),
                    None,
                )
                if not ok or written.value != len(data):
                    raise OSError(ctypes.get_last_error(), "WriteFile failed")
                kernel32.FlushFileBuffers(handle)
                kernel32.DisconnectNamedPipe(handle)
            except Exception as exc:
                self.writer_error = exc
            finally:
                kernel32.CloseHandle(handle)
                self._windows_handle = None
                self.write_complete.set()

        self.writer_thread = threading.Thread(target=write_config, daemon=True)
        self.writer_thread.start()
        return pipe_name

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.write_complete:
            self.write_complete.wait(timeout=30)
        if self._windows_handle is not None:
            try:
                import ctypes
                ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(self._windows_handle)
            except Exception:
                pass
            self._windows_handle = None
        if self.pipe_path is not None:
            try:
                if self.pipe_path.exists():
                    self.pipe_path.unlink()
            except Exception:
                pass


def find_fivetran_executable(connector_dir: Path) -> str:
    """Prefer the connector venv's fivetran executable, otherwise use PATH."""
    if os.name == "nt":
        candidates = [
            connector_dir / ".venv" / "Scripts" / "fivetran.exe",
            connector_dir / ".venv" / "Scripts" / "fivetran.cmd",
            connector_dir / ".venv" / "Scripts" / "fivetran",
        ]
    else:
        candidates = [connector_dir / ".venv" / "bin" / "fivetran"]

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    return shutil.which("fivetran") or "fivetran"


def main():
    parser = argparse.ArgumentParser(description="Deploy a connector to Fivetran")
    parser.add_argument("connector_directory", help="Path to the connector directory")
    parser.add_argument("--connection", help="Connection name (default: derived from the directory name)")
    parser.add_argument("--start-sync", action="store_true",
                        help="Unpause an already-deployed connection to start syncing (use with --connection-id)")
    parser.add_argument("--connection-id", help="Connection ID to unpause (required with --start-sync)")
    args = parser.parse_args()

    # Opt-in unpause path: start the initial sync of an already-deployed connection.
    # The build/deploy skill calls this only after the user explicitly confirms.
    if args.start_sync:
        if not args.connection_id:
            print("Error: --start-sync requires --connection-id <id>.", file=sys.stderr)
            sys.exit(1)
        unpause_connection(load_api_key(), args.connection_id)
        sys.exit(0)

    connector_dir = Path(args.connector_directory).resolve()
    if not connector_dir.exists():
        print(f"Error: Directory not found: {connector_dir}")
        sys.exit(1)

    config_path = connector_dir / "configuration.json"
    if not config_path.exists():
        print(f"Error: configuration.json not found in {connector_dir}")
        sys.exit(1)

    encrypted_content = load_encrypted_config_content(config_path)
    if not encrypted_content:
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
        config = decrypt_config(encrypted_content)
    except DecryptionFailed:
        print("Error: Failed to decrypt configuration.", file=sys.stderr)
        print("Make sure the local encryption secret matches what was used to encrypt.", file=sys.stderr)
        print(f"Expected local secret file: {SECRET_FILE}", file=sys.stderr)
        sys.exit(1)

    api_key = load_api_key()
    destination_name = discover_destination_name(api_key)
    connection_name = args.connection or sanitize_connection_name(connector_dir.name)
    print(f"Deploying as connection: {connection_name}")

    config_pipe = ConfigPipe(connector_dir, config)
    with config_pipe as pipe_path:
        cmd = [
            find_fivetran_executable(connector_dir),
            "deploy",
            "--api-key",
            api_key,
            "--destination",
            destination_name,
            "--connection",
            connection_name,
            "--configuration",
            str(pipe_path),
            # Auto-answer the "update connection / overwrite configuration?" prompts so
            # redeploys don't block waiting on stdin.
            "--force",
        ]

        connection_id = None
        process = subprocess.Popen(
            cmd,
            cwd=connector_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            universal_newlines=True
        )
        for line in process.stdout:
            print(line, end='', flush=True)
            match = re.search(r"Connection ID:\s*(\S+)", line)
            if match:
                connection_id = match.group(1)
        process.wait()

        if config_pipe.writer_error:
            print(f"Error: Failed to write configuration pipe: {config_pipe.writer_error}", file=sys.stderr)
            sys.exit(1)

        if process.returncode == 0:
            print("")
            if connection_id:
                print(f"Deployed. Connection ID: {connection_id}")
                print(f"Dashboard: https://fivetran.com/dashboard/connections/{connection_id}/status")
                print("The connection is created PAUSED. To start the initial sync (this begins")
                print("consuming MAR), run after confirming with the user:")
                print(f'  python "{SCRIPT_DIR}/deploy_connector.py" "{connector_dir}" --start-sync --connection-id {connection_id}')
            else:
                print("Deployed. The connection is created PAUSED; start the initial sync from the")
                print("Fivetran dashboard or via the REST API (the Connection ID is in the log above).")

        sys.exit(process.returncode)


if __name__ == "__main__":
    main()
