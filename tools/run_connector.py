#!/usr/bin/env python3
"""
Run a connector with protected configuration values.

Decrypts configuration values in memory and passes the full configuration to
fivetran debug via named pipe.

Usage:
    python run_connector.py <connector_directory>
"""
import json
import os
import shutil
import subprocess
import sys
import threading
import uuid
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.resolve()

ENCRYPTED_PREFIX = "ENCRYPTED:"
ENCRYPTED_TOKEN_VERSION = "v1"
ENCRYPTED_TOKEN_ALGORITHM = "local-fernet"
SECRET_FILE = Path.home() / ".fivetran" / "csdk_master_secret"
FERNET_KEY_PREFIX = "FERNET_KEY:"


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

    return decrypt_config_values(config)


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

    try:
        config = load_runtime_config(config_path)
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

    config_pipe = ConfigPipe(connector_dir, config)
    with config_pipe as pipe_path:
        cmd = [
            find_fivetran_executable(connector_dir),
            "debug",
            "--configuration",
            str(pipe_path),
        ]

        process = subprocess.Popen(
            cmd,
            cwd=connector_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            universal_newlines=True
        )

        timed_out = False

        def timeout_handler():
            nonlocal timed_out
            timed_out = True
            process.kill()

        timer = threading.Timer(60, timeout_handler)
        timer.start()

        try:
            for line in process.stdout:
                print(line, end='', flush=True)
            process.wait()
        finally:
            timer.cancel()

        if timed_out:
            print("\nError: Command timed out after 60 seconds")
            sys.exit(124)

        if config_pipe.writer_error:
            print(f"Error: Failed to write configuration pipe: {config_pipe.writer_error}", file=sys.stderr)
            sys.exit(1)

        sys.exit(process.returncode)


if __name__ == "__main__":
    main()
