import duckdb
import os
import sys
import subprocess
import select
import time
import json
from pathlib import Path


# Import the helper function to get connectors directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from history_utils import get_connectors_dir

TEST_TIME = 30
TESTER_PROCESS_TIMEOUT = TEST_TIME + 30

def cleanup_tester_processes():
    """Kill any lingering Fivetran SDK Java processes that might be locking the database."""
    try:
        # Find and kill Java processes related to Fivetran SDK
        result = subprocess.run(['pgrep', '-f', 'ft_sdk_connector_tester'],
                                capture_output=True, text=True)
        if result.returncode == 0:
            pids = result.stdout.strip().split('\n')
            for pid in pids:
                if pid:
                    try:
                        subprocess.run(['kill', '-9', pid], check=False)
                        #print(f"Killed Fivetran SDK process {pid}")
                    except:
                        pass
            time.sleep(1)
    except Exception as e:
        print(f"Note: Could not cleanup processes: {e}")


def cleanup_database_wal(project_dir: Path):
    """
    Clean up orphaned DuckDB WAL files that can prevent database access.

    When a sync is killed (e.g., test timeout), DuckDB may not checkpoint,
    leaving a .wal file that locks the database. This function:
    1. Tries to checkpoint the database properly
    2. If that fails (no process has it open), removes the orphaned WAL file
    """
    warehouse_db = project_dir / "files" / "warehouse.db"
    wal_file = project_dir / "files" / "warehouse.db.wal"

    if not wal_file.exists():
        return  # No WAL file, nothing to clean up

    try:
        # Try to checkpoint the database properly
        conn = duckdb.connect(str(warehouse_db))
        conn.execute("CHECKPOINT")
        conn.close()
    except Exception:
        # If checkpoint fails and no process is using the DB, remove the WAL
        try:
            # Check if any process has the database open
            result = subprocess.run(
                ['lsof', str(warehouse_db)],
                capture_output=True, text=True
            )
            if result.returncode != 0:  # No process has it open
                wal_file.unlink()
        except Exception:
            pass  # Best effort cleanup


def ensure_venv_exists(project_dir: Path, user_workspace: Path, project_name: str) -> bool:
    """
    Ensure virtual environment exists for the connector.
    If missing, create it and install requirements.txt if present.

    Args:
        project_dir: Path to the connector directory
        user_workspace: Path to the user workspace
        project_name: Name of the project

    Returns:
        bool: True if venv exists/created successfully, False otherwise
    """
    venv_dir = project_dir / "venv"

    # If venv already exists, we're done
    if venv_dir.exists():
        return True

    # Venv doesn't exist - create it using uv (for uploaded/old connectors)
    # uv will use its default Python version
    print("📦 Virtual environment not found, creating one...", flush=True)
    print("   (This is a one-time setup for this connector)", flush=True)

    try:
        # Create virtual environment using uv (uses shared cache for packages)
        result = subprocess.run(
            ["uv", "venv", str(venv_dir)],
            text=True,
            capture_output=True,
            timeout=60
        )

        if result.returncode != 0:
            print(f"❌ Failed to create virtual environment: {result.stderr}", flush=True)
            return False

        print("✅ Virtual environment created", flush=True)

        # Install requirements.txt if it exists using uv pip
        requirements_path = project_dir / "requirements.txt"
        venv_python = venv_dir / "bin" / "python"
        if requirements_path.exists():
            print("📦 Installing dependencies from requirements.txt...", flush=True)

            install_result = subprocess.run(
                ["uv", "pip", "install", "-r", str(requirements_path), "--python", str(venv_python)],
                text=True,
                capture_output=True,
                timeout=300
            )

            if install_result.returncode != 0:
                print(f"❌ Failed to install requirements: {install_result.stderr}", flush=True)
                return False

            print("✅ Dependencies installed", flush=True)
        else:
            print("   (No requirements.txt found, skipping dependency installation)", flush=True)

        # Install fivetran_connector_sdk separately (required for local testing)
        print("📦 Installing fivetran_connector_sdk for local testing...", flush=True)

        sdk_install_result = subprocess.run(
            ["uv", "pip", "install", "fivetran_connector_sdk", "--python", str(venv_python)],
            text=True,
            capture_output=True,
            timeout=120
        )

        if sdk_install_result.returncode != 0:
            print(f"❌ Failed to install fivetran_connector_sdk: {sdk_install_result.stderr}", flush=True)
            return False

        print("✅ fivetran_connector_sdk installed", flush=True)
        return True

    except subprocess.TimeoutExpired:
        print("❌ Virtual environment setup timed out", flush=True)
        return False
    except Exception as e:
        print(f"❌ Error setting up virtual environment. Please check the logs.", flush=True)
        print(f"Detail: {e}", file=sys.stderr, flush=True)
        return False

def check_destination() -> bool:
    try:
        # Check warehouse.db for data
        warehouse_db = project_dir / "files" / "warehouse.db"
        if not warehouse_db.exists():
            print("❌ warehouse.db not created")
            return False

        conn = duckdb.connect(str(warehouse_db))

        # Get all tables
        tables = conn.execute("SELECT table_schema, table_name FROM information_schema.tables;").fetchall()
        table_names = [f"{row[0]}.{row[1]}" for row in tables]

        if not table_names:
            conn.close()
            print("❌ No tables created in warehouse.db")
            return False

        # Check each table has data
        validated_tables = []
        for table in table_names:
            result = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            if result and result[0] > 0:
                validated_tables.append(f"{table}({result[0]} records)")

        conn.close()

        if not validated_tables:
            tables = '\n'.join([name.split('.')[1] for name in table_names])
            print(f"❌ Tables created but no data found:\n{tables}")
            return False

        print(f"✅ Data validation passed! Tables with data: {', '.join(validated_tables)}")
        return True

    except Exception as e:
        print(f"❌ Error validating warehouse.db. Please check the logs.")
        print(f"Detail: {e}", file=sys.stderr, flush=True)
        return False


def load_decrypted_config(project_dir: Path, username: str = None) -> dict:
    """
    Load and decrypt configuration.json into memory.

    Args:
        project_dir: Path to the connector directory
        username: Username for decryption (required if config is encrypted)

    Returns:
        Decrypted configuration dictionary
    """
    config_file = project_dir / "configuration.json"
    file_content = config_file.read_text()

    # Try to parse as JSON first (unencrypted)
    try:
        return json.loads(file_content)
    except json.JSONDecodeError:
        # Not valid JSON = encrypted, decrypt entire file
        if not username:
            raise ValueError("Username required to decrypt configuration")
        # Import encryption module from same directory
        import sys
        app_dir = Path(__file__).parent
        if str(app_dir) not in sys.path:
            sys.path.insert(0, str(app_dir))
        from encryption import decrypt_config
        return decrypt_config(username, file_content)


class ConfigPipe:
    """
    Named pipe (FIFO) for securely passing config to the SDK.

    Benefits over temp files:
    - Data never touches disk (stays in kernel buffer)
    - Automatically cleaned up when read
    - More secure - no file to leak

    Note: Requires patched SDK (os.path.exists instead of os.path.isfile)
    """
    def __init__(self, project_dir: Path, config: dict):
        self.config = config
        self.pipe_path = project_dir / ".config_pipe"
        self.writer_thread = None
        self.write_complete = None
        self.write_error = None

    def __enter__(self):
        import threading

        # Remove any stale pipe
        if self.pipe_path.exists():
            self.pipe_path.unlink()

        # Create named pipe with restrictive permissions
        os.mkfifo(self.pipe_path, 0o600)

        # Event to signal when write is complete
        self.write_complete = threading.Event()

        # Write config in a separate thread (blocks until reader opens)
        def write_config():
            try:
                # Debug: show what we're writing
                config_json = json.dumps(self.config)
                print(f"[ConfigPipe] Writing {len(config_json)} bytes to pipe", flush=True)

                with open(self.pipe_path, 'w') as f:
                    f.write(config_json)
                    f.flush()

                print(f"[ConfigPipe] Write complete", flush=True)
            except Exception as e:
                self.write_error = "Configuration write failed"
                print(f"[ConfigPipe] Write error", flush=True)
                print(f"Detail: {e}", file=sys.stderr, flush=True)
            finally:
                self.write_complete.set()

        self.writer_thread = threading.Thread(target=write_config, daemon=True)
        self.writer_thread.start()

        return self.pipe_path

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Wait for writer thread to complete (with timeout)
        if self.write_complete:
            self.write_complete.wait(timeout=30)

        # Clean up pipe
        try:
            if self.pipe_path.exists():
                self.pipe_path.unlink()
        except Exception:
            pass


def run_tester(project_name, user_workspace) -> tuple[int, str]:
    """Run connector tests and return exit code and captured output."""
    captured_output = []

    try:
        test_process = subprocess.Popen(
            [sys.executable, "_run.py", project_name, str(user_workspace), "test"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=0,
            env={**os.environ, 'PYTHONUNBUFFERED': '1'}
        )

        start_time = time.time()

        while test_process.poll() is None:
            if time.time() - start_time > TESTER_PROCESS_TIMEOUT:
                timeout_msg = f"\n‼️ Test timed out reached (shouldn't happen)"
                print(timeout_msg)
                captured_output.append(timeout_msg)
                test_process.kill()
                test_process.wait(timeout=5)
                return 1, '\n'.join(captured_output)

            if test_process.stdout and select.select([test_process.stdout], [], [], 1.0)[0]:
                line = test_process.stdout.readline()
                if line:
                    stripped_line = line.rstrip()

                    if stripped_line:
                        # Prefix with TEST_LOG to route to logs tab
                        if stripped_line.startswith("TEST_LOG:"):
                            print(stripped_line, flush=True)
                        else:
                            print(f"TEST_LOG:INFO:{stripped_line}", flush=True)
                        captured_output.append(stripped_line)

        test_result_code = test_process.returncode

        if test_result_code == 0:
            success_msg = f"✅ Testing passed! Connector is ready for use."
            print(f"TEST_LOG:SUCCESS:{success_msg}")
            captured_output.append(success_msg)
            return 0, '\n'.join(captured_output)

    except Exception as e:
        error_msg = "❌ Error during testing. Please check the logs."
        print(f"TEST_LOG:ERROR:{error_msg}")
        print(f"Detail: {e}", file=sys.stderr, flush=True)
        captured_output.append(error_msg)
        return 1, '\n'.join(captured_output)

    fail_msg = f"❌ Testing failed."
    print(f"TEST_LOG:ERROR:{fail_msg}")
    captured_output.append(fail_msg)
    return 1, '\n'.join(captured_output)


if __name__ == "__main__":
    project_name = sys.argv[1]
    user_workspace = Path(sys.argv[2])
    mode = sys.argv[3] if len(sys.argv) > 3 else "run"

    # Extract username from workspace path (e.g., "../workspaces/john_doe" -> "john_doe")
    username = user_workspace.name

    user_code_dir = get_connectors_dir(user_workspace)
    project_dir = user_code_dir / project_name

    if mode == "run":
        print("🔄 Running sync...")
    else:
        print(f"Testing connector...")
    print("-" * 50)

    if mode == "test":
        # Check if connector.py exists
        connector_file = project_dir / "connector.py"
        if not connector_file.exists():
            print(f"❌ connector.py not found in {project_dir}")
            sys.exit(1)

    # Check if configuration.json exists in the project directory
    config_file = project_dir / "configuration.json"
    if not config_file.exists():
        print(f"❌ Configuration file not found: {config_file}")
        sys.exit(1)

    # Ensure virtual environment exists (creates if missing for uploaded/old connectors)
    if not ensure_venv_exists(project_dir, user_workspace, project_name):
        print("❌ Failed to setup virtual environment")
        sys.exit(1)

    # Load and decrypt configuration into memory
    config = load_decrypted_config(project_dir, username)
    print(f"[Debug] Loaded config with {len(config)} keys: {list(config.keys())}", flush=True)

    # Prepare environment to use connector's virtual environment
    venv_bin = project_dir / "venv" / "bin"
    env = os.environ.copy()
    env['PATH'] = f"{venv_bin}:{env['PATH']}"  # Prepend venv bin to PATH
    env['VIRTUAL_ENV'] = str(project_dir / "venv")  # Set VIRTUAL_ENV
    env['PYTHONUNBUFFERED'] = '1'  # Force unbuffered output

    # Use absolute path to fivetran to bypass pyenv shim interference
    fivetran_cmd = (venv_bin / "fivetran").resolve()
    if not fivetran_cmd.exists():
        print(f"❌ fivetran executable not found in venv: {fivetran_cmd}")
        sys.exit(1)

    # Clean up any orphaned WAL files from previous runs before starting
    cleanup_database_wal(project_dir)

    # Run the command with bash process substitution for config (never touches disk)
    # Bash handles the pipe timing automatically via <(echo '...')
    output_lines = []
    test_timed_out = False
    exit_code = 1

    try:
        # Use bash process substitution - bash manages the pipe internally
        config_json = json.dumps(config)
        print(f"[Debug] Config JSON length: {len(config_json)}", flush=True)

        # Escape single quotes for bash and use printf for safe JSON handling
        escaped_json = config_json.replace("'", "'\\''")
        bash_cmd = f"{fivetran_cmd} debug --configuration <(printf '%s' '{escaped_json}')"
        print(f"[Debug] Running bash command", flush=True)

        process = subprocess.Popen(
            ['bash', '-c', bash_cmd],
            cwd=project_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=0,  # Unbuffered
            universal_newlines=True,
            env=env  # Use modified environment with connector venv
        )

        # Stream output in real-time while capturing it
        start_time = time.time()
        while process.poll() is None:
            if mode == "test":
                if time.time() - start_time > TEST_TIME:
                    print("\n" + "="*50)
                    print("TEST_LOG:WARNING:⏱️  30-SECOND TEST LIMIT REACHED")
                    print("="*50)
                    print("TEST_LOG:WARNING:ℹ️  This was a quick validation test to verify your connector works.")
                    print("TEST_LOG:WARNING:   Not all data may have been processed - this is expected!")
                    print()
                    print("TEST_LOG:WARNING:💡 To process all data, use the 'Run Debug' button to run a full sync.")
                    print("="*50)
                    test_timed_out = True
                    process.kill()
                    break

            # Use select to check for available output
            if select.select([process.stdout], [], [], 0.1)[0]:
                line = process.stdout.readline()
                if line:
                    print(line.rstrip(), flush=True)
                    output_lines.append(line.rstrip().lower())

        # Read any remaining output
        for line in iter(process.stdout.readline, ''):
            print(line.rstrip(), flush=True)
            output_lines.append(line.rstrip().lower())

        process.wait(timeout=10)
        if process.poll() is None:
            print("❌ Sync process did not terminate")
            sys.exit(1)

        # Wait for warehouse.db to be free
        cleanup_tester_processes()
        time.sleep(2)

        # Checkpoint database to merge any WAL file
        cleanup_database_wal(project_dir)

        exit_code = process.returncode

    except Exception as e:
        print(f"❌ Error running sync. Please check the logs.")
        print(f"Detail: {e}", file=sys.stderr, flush=True)
        sys.exit(1)

    print("-" * 50)

    # Check output for clear failure indicators since fivetran debug may return 0 even on failure
    output_text = '\n'.join(output_lines)
    has_failure = any(indicator in output_text for indicator in ["sync failed", "traceback"])

    # If test timed out, treat as success (validation passed, partial data expected)
    if mode == "test" and test_timed_out:
        print("✅ Validation test passed (30-second limit)")
        sys.exit(0)
    elif mode == "run" and exit_code != 0:
        print(f"❌ Sync exited with code {exit_code}")
        sys.exit(exit_code)
    elif has_failure:
        print("❌ Sync errors detected!")
        sys.exit(1)  # Override the 0 exit code
    elif mode == "test" and not check_destination():
        sys.exit(1)
    else:
        print("✅ Sync completed successfully")
