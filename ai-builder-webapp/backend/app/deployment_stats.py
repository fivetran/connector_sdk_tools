import csv
import os
from pathlib import Path
from datetime import datetime
import fcntl  # For file locking on Unix

DEPLOYMENT_LOG_FILE = Path("workspaces/deployment_log.csv")
CSV_HEADERS = ["username", "project_name", "connector_name", "destination_name", "timestamp"]

def ensure_log_file_exists():
    """Create CSV file with headers if it doesn't exist."""
    if not DEPLOYMENT_LOG_FILE.exists():
        DEPLOYMENT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(DEPLOYMENT_LOG_FILE, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writeheader()

def log_successful_deployment(
    username: str,
    project_name: str,
    connector_name: str,
    destination_name: str
):
    """Append a successful deployment entry to the CSV log."""
    try:
        ensure_log_file_exists()

        timestamp = datetime.utcnow().isoformat() + 'Z'

        with open(DEPLOYMENT_LOG_FILE, 'a', newline='') as f:
            # File locking for concurrent writes (Unix only)
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            except (AttributeError, OSError):
                pass  # Windows or lock not supported

            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writerow({
                'username': username,
                'project_name': project_name,
                'connector_name': connector_name,
                'destination_name': destination_name,
                'timestamp': timestamp
            })

            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except (AttributeError, OSError):
                pass

    except Exception as e:
        # Don't break deployment if logging fails
        print(f"Warning: Failed to log deployment: {e}")
