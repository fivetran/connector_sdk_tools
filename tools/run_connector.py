#!/usr/bin/env python3
"""
Run a connector with protected configuration values.

Decrypts configuration values in memory and passes the full configuration to
fivetran debug via named pipe.

Usage:
    python run_connector.py <connector_directory> [--timeout-seconds SECONDS]
"""
import argparse
import errno
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
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

    for field, value in config.items():
        if not isinstance(value, str):
            raise ValueError(
                f"Configuration field {field!r} must be a string; "
                "nested objects, arrays, numbers, booleans, and null are not supported."
            )
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
                handle = kernel32.OpenThread(0x0001, False, self.writer_thread.native_id)
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
                else:
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


class WindowsJob:
    """Own a Windows process tree independently of any member's lifetime."""

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        class BasicLimits(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BasicLimits),
                ("IoInfo", ctypes.c_uint64 * 6),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        self.kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        self.kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
        self.kernel32.SetInformationJobObject.restype = wintypes.BOOL
        self.kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.kernel32.OpenProcess.restype = wintypes.HANDLE
        self.kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        self.kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel32.CloseHandle.restype = wintypes.BOOL
        self.lock = threading.Lock()
        self.handle = self.kernel32.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        if not self.kernel32.SetInformationJobObject(
                self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def assign(self, pid):
        import ctypes
        # PROCESS_SET_QUOTA | PROCESS_TERMINATE
        handle = self.kernel32.OpenProcess(0x0100 | 0x0001, False, pid)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not self.kernel32.AssignProcessToJobObject(self.handle, handle):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            self.kernel32.CloseHandle(handle)

    def close(self):
        with self.lock:
            if self.handle:
                if not self.kernel32.CloseHandle(self.handle):
                    import ctypes
                    raise ctypes.WinError(ctypes.get_last_error())
                self.handle = None


def run_debug(cmd, connector_dir, timeout_seconds):
    process = None
    job = None
    timer = None
    timed_out = threading.Event()
    previous_handlers = {}

    def stop_tree():
        if job is not None:
            job.close()
        if process is not None:
            if os.name == "nt":
                # Also handles failure to assign the gated launcher to the job.
                if process.poll() is None:
                    process.kill()
            else:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def timeout_handler():
        timed_out.set()
        stop_tree()

    def interrupted(signum, _frame):
        raise SystemExit(128 + signum)

    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signum] = signal.signal(signum, interrupted)
        if os.name == "nt":
            job = WindowsJob()
            # The launcher cannot spawn the SDK until job assignment succeeds.
            # Descendants inherit job membership, even after the launcher exits.
            launcher = (
                "import subprocess, sys; "
                "gate = sys.stdin.buffer.read(1); "
                "sys.exit(subprocess.call(sys.argv[1:], stdin=subprocess.DEVNULL) "
                "if gate == b'1' else 1)"
            )
            cmd = [sys.executable, "-c", launcher, *cmd]
        process = subprocess.Popen(
            cmd, cwd=connector_dir, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, bufsize=1, universal_newlines=True,
            stdin=subprocess.PIPE if job is not None else None,
            start_new_session=(os.name != "nt"),
            creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
        )
        if job is not None:
            job.assign(process.pid)
            process.stdin.write("1")
            process.stdin.close()
        timer = threading.Timer(timeout_seconds, timeout_handler)
        timer.start()
        for line in process.stdout:
            print(line, end='', flush=True)
        process.wait()
    finally:
        # A second interrupt must not interrupt cleanup halfway through.
        for signum in previous_handlers:
            signal.signal(signum, signal.SIG_IGN)
        try:
            if timer is not None:
                timer.cancel()
                timer.join()
            stop_tree()
            if process is not None:
                process.wait()
                if process.stdin is not None:
                    process.stdin.close()
                process.stdout.close()
        finally:
            for signum, handler in previous_handlers.items():
                signal.signal(signum, handler)
    if timed_out.is_set():
        raise subprocess.TimeoutExpired(cmd, timeout_seconds)
    return process.returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("connector_directory", type=Path)
    parser.add_argument(
        "--timeout-seconds", type=int, default=120,
        help="Debug time limit in seconds (default: 120; maximum: 600).",
    )
    args = parser.parse_args()
    if not 0 < args.timeout_seconds <= 600:
        parser.error("--timeout-seconds must be between 1 and 600")

    connector_dir = args.connector_directory.resolve()

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

        try:
            returncode = run_debug(cmd, connector_dir, args.timeout_seconds)
        except subprocess.TimeoutExpired:
            print(f"\nError: Command timed out after {args.timeout_seconds} seconds")
            sys.exit(124)

        if config_pipe.writer_error:
            print(f"Error: Failed to write configuration pipe: {config_pipe.writer_error}", file=sys.stderr)
            sys.exit(1)

        sys.exit(returncode)


if __name__ == "__main__":
    main()
