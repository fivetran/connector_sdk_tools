#!/usr/bin/env python3
"""
Deploy a connector to Fivetran.

Reads FIVETRAN_API_KEY from env, resolves an existing connection or an explicit
destination, then passes local configuration to `fivetran deploy` via a
named pipe after decrypting configuration values in memory. Without a local
configuration file, the SDK resolves configuration normally.

Usage:
    python deploy_connector.py "<connector_directory>" --connection-id "<id>"
    python deploy_connector.py "<connector_directory>" --destination "<name>" --connection "<name>"
    python deploy_connector.py "<connector_directory>" --start-sync --connection-id "<id>"
    python deploy_connector.py --help
"""
import argparse
import errno
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import nullcontext
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()
API_BASE = "https://api.fivetran.com/v1"

ENCRYPTED_PREFIX = "ENCRYPTED:"
ENCRYPTED_TOKEN_VERSION = "v1"
ENCRYPTED_TOKEN_ALGORITHM = "local-fernet"
SECRET_FILE = Path.home() / ".fivetran" / "csdk_master_secret"
FERNET_KEY_PREFIX = "FERNET_KEY:"


class DecryptionFailed(Exception):
    """Raised when encrypted configuration cannot be decrypted."""


class ApiError(Exception):
    """Raised when a Fivetran REST API call fails."""
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


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
        try:
            SECRET_FILE.parent.chmod(0o700)
            SECRET_FILE.chmod(0o600)
        except OSError:
            pass
        master_secret = SECRET_FILE.read_text().strip()
        if parse_master_secret(master_secret):
            return master_secret
        print("Unsupported local encryption secret format.", file=sys.stderr)
        print("", file=sys.stderr)
        print("Run enter_configuration.py in a separate terminal to create a new secret", file=sys.stderr)
        print("and rewrite configuration values in configuration.json.", file=sys.stderr)
        sys.exit(1)

    print("No local encryption secret found.", file=sys.stderr)
    print("", file=sys.stderr)
    print("Run enter_configuration.py in a separate terminal first. It will", file=sys.stderr)
    print(f"create {SECRET_FILE} and encrypt configuration values in configuration.json.", file=sys.stderr)
    sys.exit(1)


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


def get_encryption_key() -> tuple[str, bytes]:
    """Return the local Fernet key id and key."""
    master_secret = load_master_secret()
    parsed = parse_master_secret(master_secret)
    if parsed is None:
        raise DecryptionFailed
    return parsed


def decrypt_value(encrypted_content: str) -> str:
    """Decrypt a single encrypted value."""
    Fernet, InvalidToken = get_fernet()
    local_key_id, key = get_encryption_key()
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


def decrypt_config_values(config: dict) -> dict:
    """Decrypt inline encrypted fields and pass plaintext values through."""
    runtime_config = {}

    for field, value in config.items():
        if isinstance(value, str) and value.startswith(ENCRYPTED_PREFIX):
            try:
                runtime_config[field] = decrypt_value(value)
            except DecryptionFailed as exc:
                raise DecryptionFailed(f"Failed to decrypt configuration field {field!r}.") from exc
        else:
            runtime_config[field] = value

    return runtime_config


def load_runtime_config(config_path: Path) -> dict:
    content = config_path.read_text().strip()

    try:
        config = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {config_path}: {exc}") from exc

    if not isinstance(config, dict):
        raise ValueError(f"{config_path} must contain a JSON object.")

    for field, value in config.items():
        if not isinstance(value, str):
            raise ValueError(
                f"Configuration field {field!r} must be a string; "
                "nested objects, arrays, numbers, booleans, and null are not supported."
            )
    return decrypt_config_values(config)


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
        lines = [f"Fivetran API {method} {path} returned {e.code}."]
        if e.code in (401, 403):
            lines.append("Your FIVETRAN_API_KEY is missing or lacks required permissions.")
            lines.append("It must be the base64-encoded '{key}:{secret}' string.")
        if err_body:
            lines.append(f"Response: {err_body[:500]}")
        raise ApiError("\n".join(lines), status_code=e.code) from e
    except urllib.error.URLError as e:
        raise ApiError(f"Could not reach Fivetran API ({e.reason}).") from e


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
        except EOFError:
            print("Error: Input closed before a destination was selected. "
                  "Use --connection-id or --destination.", file=sys.stderr)
            sys.exit(1)
        except ValueError:
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


def existing_connection_target(api_key: str, connection_id: str) -> tuple[str, str, bool]:
    """Resolve the authoritative connection name, destination, and paused state for a redeployment."""
    try:
        connection = fivetran_get(
            f"/connections/{urllib.parse.quote(connection_id, safe='')}", api_key,
        ).get("data", {})
    except ApiError as exc:
        if exc.status_code == 404:
            raise ValueError(f"--connection-id {connection_id!r} was not found.") from exc
        raise
    if connection.get("service") != "connector_sdk":
        raise ValueError("--connection-id must identify a Connector SDK connection.")
    group_id = connection.get("group_id")
    name = connection.get("schema")
    if not isinstance(group_id, str) or not group_id or not isinstance(name, str) or not name:
        raise ValueError("Connection details did not include its group_id and schema; deployment stopped.")
    group = fivetran_get(
        f"/groups/{urllib.parse.quote(group_id, safe='')}", api_key,
    ).get("data", {})
    destination = group.get("name")
    if not isinstance(destination, str) or not destination:
        raise ValueError("Group details did not include its name; deployment stopped.")
    return name, destination, bool(connection.get("paused"))


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
    """
    Named pipe for securely passing config to the SDK.
    Data never touches disk - stays in kernel/OS pipe buffers.
    """
    def __init__(self, project_dir: Path, config: dict):
        self.config = config
        self.project_dir = project_dir
        self.pipe_path = None
        self.writer_thread = None
        self.write_complete = None
        self.writer_error = None
        self._windows_handle = None
        self.cancelled = threading.Event()

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
            fd = None
            try:
                while not self.cancelled.is_set():
                    try:
                        fd = os.open(self.pipe_path, os.O_WRONLY | os.O_NONBLOCK)
                        break
                    except OSError as exc:
                        if exc.errno != errno.ENXIO:
                            raise
                        self.cancelled.wait(0.05)
                data = memoryview(json.dumps(self.config).encode("utf-8"))
                while fd is not None and data and not self.cancelled.is_set():
                    try:
                        data = data[os.write(fd, data):]
                    except BlockingIOError:
                        self.cancelled.wait(0.05)
                if fd is not None and data and self.cancelled.is_set():
                    self.writer_error = RuntimeError(
                        f"configuration write cancelled with {len(data)} byte(s) unsent; "
                        "the connector may have received truncated configuration"
                    )
            except Exception as exc:
                if not self.cancelled.is_set():
                    self.writer_error = exc
            finally:
                if fd is not None:
                    os.close(fd)
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
                if self.cancelled.is_set():
                    return
                connected = kernel32.ConnectNamedPipe(handle, None)
                if not connected:
                    err = ctypes.get_last_error()
                    if err != error_pipe_connected:
                        raise OSError(err, "ConnectNamedPipe failed")

                if self.cancelled.is_set():
                    return
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
                if self.cancelled.is_set():
                    return
                kernel32.FlushFileBuffers(handle)
                kernel32.DisconnectNamedPipe(handle)
            except Exception as exc:
                if not self.cancelled.is_set():
                    self.writer_error = exc
            finally:
                kernel32.CloseHandle(handle)
                self._windows_handle = None
                self.write_complete.set()

        self.writer_thread = threading.Thread(target=write_config, daemon=True)
        self.writer_thread.start()
        return pipe_name

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cancelled.set()
        cleanup_error = None
        if self.writer_thread is not None:
            if os.name == "nt" and self.writer_thread.is_alive():
                import ctypes
                from ctypes import wintypes
                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel32.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
                kernel32.OpenThread.restype = wintypes.HANDLE
                kernel32.CancelSynchronousIo.argtypes = [wintypes.HANDLE]
                kernel32.CancelSynchronousIo.restype = wintypes.BOOL
                kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
                native_id = self.writer_thread.native_id
                # native_id can be recycled once the thread exits; re-check aliveness
                # right up to (and right after) the OpenThread call to shrink, though
                # not eliminate, that race.
                handle = kernel32.OpenThread(0x0001, False, native_id) if self.writer_thread.is_alive() else None
                thread_already_done = not self.writer_thread.is_alive()
                if handle and thread_already_done:
                    # Thread finished between the is_alive() check and OpenThread;
                    # the handle may reference an unrelated, recycled thread. Drop it.
                    kernel32.CloseHandle(handle)
                    handle = None
                if handle:
                    try:
                        # Retry to cover cancellation between the writer's stop
                        # check and its next blocking I/O call. The writer alone
                        # owns/closes the pipe handle.
                        deadline = time.monotonic() + 1
                        while self.writer_thread.is_alive() and time.monotonic() < deadline:
                            if not kernel32.CancelSynchronousIo(handle):
                                error = ctypes.get_last_error()
                                if error != 1168:  # ERROR_NOT_FOUND: no pending I/O yet
                                    cleanup_error = f"CancelSynchronousIo failed (Windows error {error})"
                                    break
                            self.writer_thread.join(0.05)
                    finally:
                        kernel32.CloseHandle(handle)
                elif not thread_already_done:
                    cleanup_error = "OpenThread failed; could not cancel the configuration writer"
            else:
                self.writer_thread.join(timeout=1)
            if self.writer_thread.is_alive():
                detail = cleanup_error or "configuration writer did not stop within the cleanup deadline"
                print(f"Warning: {detail}. Its pipe may remain open until this process exits.",
                      file=sys.stderr)
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
    parser.add_argument("--destination", help="Destination (group) name for a new deployment")
    parser.add_argument("--start-sync", action="store_true",
                        help="Unpause an already-deployed connection to start syncing (use with --connection-id)")
    parser.add_argument("--connection-id", help="Existing connection ID to redeploy, or unpause with --start-sync")
    args = parser.parse_args()
    if args.connection_id and (args.connection or args.destination):
        parser.error("--connection-id cannot be combined with --connection or --destination; "
                     "the existing connection determines both.")

    # Opt-in unpause path: start the initial sync of an already-deployed connection.
    # The build/deploy skill calls this only after the user explicitly confirms.
    if args.start_sync:
        if not args.connection_id:
            print("Error: --start-sync requires --connection-id <id>.", file=sys.stderr)
            sys.exit(1)
        try:
            unpause_connection(load_api_key(), args.connection_id)
        except ApiError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
        sys.exit(0)

    connector_dir = Path(args.connector_directory).resolve()
    if not connector_dir.exists():
        print(f"Error: Directory not found: {connector_dir}")
        sys.exit(1)

    config_path = connector_dir / "configuration.json"
    try:
        config = load_runtime_config(config_path) if config_path.exists() else None
    except DecryptionFailed as exc:
        print("Error: Failed to decrypt configuration.", file=sys.stderr)
        if str(exc):
            print(str(exc), file=sys.stderr)
        print("Make sure the local encryption secret matches what was used to encrypt.", file=sys.stderr)
        print(f"Expected local secret file: {SECRET_FILE}", file=sys.stderr)
        sys.exit(1)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    api_key = load_api_key()
    # For a brand-new deployment there's no existing connection to check, so assume
    # paused (new connections are created paused) and keep showing the guidance below.
    connection_still_paused = True
    if args.connection_id:
        try:
            connection_name, destination_name, connection_still_paused = existing_connection_target(
                api_key, args.connection_id,
            )
        except (ValueError, ApiError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
    else:
        try:
            destination_name = args.destination or discover_destination_name(api_key)
        except ApiError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
        connection_name = args.connection or sanitize_connection_name(connector_dir.name)
    print(f"Destination: {destination_name}")
    print(f"Deploying as connection: {connection_name}")

    # Without a local file, leave configuration resolution to the SDK, including
    # FIVETRAN_CONFIGURATION. No supplied configuration preserves existing values.
    config_pipe = ConfigPipe(connector_dir, config) if config is not None else None
    with config_pipe if config_pipe is not None else nullcontext() as pipe_path:
        cmd = [
            find_fivetran_executable(connector_dir),
            "deploy",
            "--destination",
            destination_name,
            "--connection",
            connection_name,
            # Auto-answer the "update connection / overwrite configuration?" prompts so
            # redeploys don't block waiting on stdin.
            "--force",
        ]

        if pipe_path is not None:
            cmd.extend(["--configuration", str(pipe_path)])

        connection_id = args.connection_id
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

        if config_pipe is not None and config_pipe.writer_error:
            print(f"Error: Failed to write configuration pipe: {config_pipe.writer_error}", file=sys.stderr)
            sys.exit(1)

        if process.returncode == 0:
            print("")
            if connection_id:
                print(f"Deployed. Connection ID: {connection_id}")
                print(f"Dashboard: https://fivetran.com/dashboard/connections/{connection_id}/status")
                if connection_still_paused:
                    print("If the connection is paused, start syncing (consumes MAR) only after")
                    print("confirming with the user:")
                    print(f'  python "{SCRIPT_DIR}/deploy_connector.py" "{connector_dir}" --start-sync --connection-id {connection_id}')
            else:
                print("Deployed. Check connection status in the Fivetran dashboard.")
                print("If the connection is paused, start the initial sync (consumes MAR) only after")
                print("confirming with the user. Open the connection in the dashboard to start syncing,")
                print("or copy its connection ID and run:")
                print(f'  python "{SCRIPT_DIR}/deploy_connector.py" "{connector_dir}" --start-sync --connection-id "<connection_id>"')

        sys.exit(process.returncode)


if __name__ == "__main__":
    main()
