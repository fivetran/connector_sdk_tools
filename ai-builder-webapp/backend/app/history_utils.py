"""Utility functions for workspace management and session persistence."""
import json
import os
import re
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

from config import BASE_DIR


def get_connectors_dir(user_workspace: Path) -> Path:
    """Get the connectors directory from user workspace."""
    return user_workspace / "connectors"


def validate_username(username: str) -> bool:
    """Validate username to prevent path traversal attacks."""
    return bool(re.match(r'^[a-z0-9_]+$', username))


def get_user_workspace(username: str) -> Dict[str, Path]:
    """Get workspace paths for a user. Does NOT create directories.

    Directory creation should only happen via ensure_workspace_exists()
    in main.py which is called after proper authentication during login.
    """
    if not validate_username(username):
        raise ValueError(f"Invalid username format: {username}")
    user_dir = BASE_DIR / username

    structure = {
        "base": user_dir,
        "connectors": user_dir / "connectors",
    }

    # Only return paths, do NOT create directories here
    return structure


def extract_username_from_user_dir(user_code_dir: Path) -> str:
    """Extract username from user_code_dir path like 'workspaces/username/connectors' -> 'username'."""
    if user_code_dir.name == "connectors" and user_code_dir.parent.parent.name == "workspaces":
        return user_code_dir.parent.name  # Extract username from workspaces/username/connectors
    else:
        raise ValueError(f"Invalid user_code_dir path format: {user_code_dir}. Expected: workspaces/username/connectors")


def get_python_executable() -> str:
    """
    Get the Python executable path.
    Falls back to sys.executable if python3 not found.

    Returns:
        Path to Python executable
    """
    import sys
    import subprocess

    python_cmd = "python3"

    try:
        # Check if python3 exists
        result = subprocess.run([python_cmd, "--version"],
                               capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return python_cmd
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback to sys.executable
    return sys.executable


# Session ID persistence functions

def get_session_file_path(project_dir: Path) -> Path:
    """Get the session file path for a project."""
    return project_dir / "session.json"


def save_session_id(project_dir: Path, session_id: str) -> bool:
    """Save session ID to the project directory.

    Args:
        project_dir: Path to the project directory
        session_id: The Claude session ID to save

    Returns:
        True if saved successfully, False otherwise
    """
    session_file = get_session_file_path(project_dir)

    session_data = {
        "session_id": session_id,
        "last_updated": datetime.now().isoformat()
    }

    try:
        with open(session_file, 'w') as f:
            json.dump(session_data, f, indent=2)
        return True
    except IOError as e:
        print(f"Warning: Could not save session ID: {e}")
        return False


def load_session_id(project_dir: Path) -> Optional[str]:
    """Load session ID from the project directory.

    Args:
        project_dir: Path to the project directory

    Returns:
        The session ID if found, None otherwise
    """
    session_file = get_session_file_path(project_dir)

    if not session_file.exists():
        return None

    try:
        with open(session_file, 'r') as f:
            data = json.load(f)
            return data.get('session_id')
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Could not load session ID: {e}")
        return None


def clear_session_id(project_dir: Path) -> bool:
    """Clear the session ID file for a project.

    Args:
        project_dir: Path to the project directory

    Returns:
        True if cleared successfully or file didn't exist, False on error
    """
    session_file = get_session_file_path(project_dir)

    if not session_file.exists():
        return True

    try:
        session_file.unlink()
        return True
    except Exception as e:
        print(f"Warning: Could not clear session ID: {e}")
        return False
