from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Depends, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from pathlib import Path
import json
import uuid
import secrets
import logging
import re
import asyncio
import subprocess
import sys
import os
import shutil
import signal
import atexit
import time
import zipfile
import io
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import duckdb
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

# Add app directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Import validation functions
from _validate import get_validation_claude_options, validate_description

# Import credential merging functions for deploy
from _run import load_decrypted_config, ConfigPipe

# Import session persistence functions
from history_utils import save_session_id, load_session_id

# Note: encryption functions (encrypt_config, decrypt_config) are imported locally where needed

# Import centralized config
from config import (
    BASE_DIR, ENV_ANTHROPIC_API_KEY, ENV_ANTHROPIC_API_KEY_FALLBACK,
    ENV_GOOGLE_CLIENT_ID, ENV_ALLOWED_DOMAINS, ENV_ALLOWED_ORIGINS
)

app = FastAPI(title="New Connector Backend")


def log_and_format_error(e: Exception, context: str) -> str:
    """Log full error with a unique ID and return a user-friendly message.

    The error ID lets support correlate the user's report with the full
    stack trace in server logs. The actual exception details are only logged
    server-side, not returned to the client.
    """
    error_id = uuid.uuid4().hex[:8]
    logger.error(f"[{error_id}] {context}: {type(e).__name__}: {e}", exc_info=True)
    # Only return error ID to client - no exception details (security)
    return f"An error occurred. Reference ID: {error_id}"


# Rate limiting configuration
# Custom key function that properly handles X-Forwarded-For behind nginx
def get_client_ip(request: Request) -> str:
    """Get real client IP, handling reverse proxy headers."""
    # Check X-Forwarded-For header (set by nginx)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # X-Forwarded-For can contain multiple IPs; first is the real client
        return forwarded_for.split(",")[0].strip()
    # Fall back to direct connection IP
    if request.client:
        return request.client.host
    return "127.0.0.1"

limiter = Limiter(key_func=get_client_ip)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch any unhandled exception, log it with an ID, and return a useful response."""
    error_msg = log_and_format_error(exc, "Unhandled error")
    return JSONResponse(
        status_code=500,
        content={"detail": error_msg}
    )


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# CORS Configuration - restrict to known frontend origins
_allowed_origins = os.getenv(ENV_ALLOWED_ORIGINS, "").strip()
if not _allowed_origins:
    raise RuntimeError(f"{ENV_ALLOWED_ORIGINS} environment variable must be set (comma-separated origins)")
ALLOWED_ORIGINS_LIST = _allowed_origins.split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS_LIST,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
)

# Session management
SESSION_EXPIRE_HOURS = 48  # Extended to 48 hours for long-running jobs

# Google OAuth Configuration
GOOGLE_CLIENT_ID = os.getenv(ENV_GOOGLE_CLIENT_ID)
_allowed_domains_raw = os.getenv(ENV_ALLOWED_DOMAINS)
if not _allowed_domains_raw:
    raise RuntimeError(f"{ENV_ALLOWED_DOMAINS} environment variable is required")
ALLOWED_DOMAINS_LIST = _allowed_domains_raw.split(",")


def get_anthropic_api_key() -> str | None:
    """Get Anthropic API key with fallback."""
    return os.getenv(ENV_ANTHROPIC_API_KEY) or os.getenv(ENV_ANTHROPIC_API_KEY_FALLBACK)


# ANSI escape code pattern for stripping color codes from output
ANSI_ESCAPE_PATTERN = re.compile(r'\x1b\[[0-9;]*m')

def strip_ansi_codes(text: str) -> str:
    """Remove ANSI escape codes (color codes) from text."""
    return ANSI_ESCAPE_PATTERN.sub('', text)


# In-memory session storage (in production, use Redis or database)
active_sessions = {}

# Active generation processes storage
active_processes = {}

# Note: Interact sessions are persisted to project directories via save_session_id/load_session_id
# Note: Validation sessions intentionally do NOT use session resumption - each validation starts fresh

# Session credentials storage (maps "session_token:project_name" to config values)
# This is a runtime cache for the UI. Scripts decrypt configuration.json directly when needed.
session_credentials = {}
credentials_lock = threading.Lock()

def get_credentials_for_project(session_token: str, project_name: str) -> dict:
    """Get credentials from memory cache (for UI display purposes)."""
    credentials_key = f"{session_token}:{project_name}"

    with credentials_lock:
        if credentials_key in session_credentials:
            return session_credentials[credentials_key]

    return {}

# Session cancellation tracking (maps "session_token:project_name" to cancellation flag)
session_cancellations = {}
cancellation_lock = threading.Lock()

# Process management enhancements
def cleanup_connector_processes():
    """Kill any lingering connector or SDK processes that might be locking resources."""
    try:
        # Find and kill processes related to connector testing
        result = subprocess.run(['pgrep', '-f', 'fivetran'], 
                               capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            pids = result.stdout.strip().split('\n')
            for pid in pids:
                if pid:
                    try:
                        subprocess.run(['kill', '-9', pid], check=False, timeout=2)
                        print(f"Killed connector process {pid}")
                    except:
                        pass
            time.sleep(0.5)  # Brief pause for cleanup
    except Exception as e:
        print(f"Note: Could not cleanup connector processes: {e}")

def terminate_process_gracefully(process, timeout=10):
    """Terminate a process gracefully with escalation to SIGKILL if needed."""
    if process is None or process.poll() is not None:
        return True  # Process already terminated
    
    try:
        # Try to terminate the entire process group first (if available)
        if os.name != 'nt':  # Unix-like systems
            try:
                # Get process group ID
                pgid = os.getpgid(process.pid)
                # Terminate entire process group
                os.killpg(pgid, signal.SIGTERM)
                print(f"Sent SIGTERM to process group {pgid}")
            except (OSError, ProcessLookupError):
                # Fall back to individual process termination
                process.terminate()
        else:
            # Windows - just terminate the process
            process.terminate()
        
        # Wait for graceful termination with timeout
        try:
            process.wait(timeout=timeout)
            return True
        except subprocess.TimeoutExpired:
            # Graceful termination failed, force kill
            print(f"Process {process.pid} did not terminate gracefully, forcing kill")
            if os.name != 'nt':
                try:
                    # Force kill the entire process group
                    pgid = os.getpgid(process.pid)
                    os.killpg(pgid, signal.SIGKILL)
                    print(f"Sent SIGKILL to process group {pgid}")
                except (OSError, ProcessLookupError):
                    process.kill()
            else:
                process.kill()
            
            try:
                process.wait(timeout=5)
                return True
            except subprocess.TimeoutExpired:
                print(f"Warning: Process {process.pid} could not be killed")
                return False
    except Exception as e:
        print(f"Error terminating process: {e}")
        return False

def terminate_process_immediately(process):
    """Terminate a process immediately using SIGKILL (for user-initiated stops)."""
    if process is None or process.poll() is not None:
        return True  # Process already terminated

    try:
        if os.name != 'nt':  # Unix-like systems
            try:
                # Kill entire process group immediately
                pgid = os.getpgid(process.pid)
                os.killpg(pgid, signal.SIGKILL)
                print(f"Sent SIGKILL to process group {pgid}")
            except (OSError, ProcessLookupError):
                # Fall back to individual process kill
                process.kill()
        else:
            # Windows - just kill the process
            process.kill()

        # Wait briefly for process to die
        try:
            process.wait(timeout=1)
            return True
        except subprocess.TimeoutExpired:
            print(f"Warning: Process {process.pid} did not die after SIGKILL")
            return False
    except Exception as e:
        print(f"Error killing process immediately: {e}")
        return False

def cleanup_all_processes():
    """Clean up all active processes on server shutdown."""
    print("Cleaning up all active processes...")

    # Terminate all tracked processes
    for process_key, process in list(active_processes.items()):
        try:
            if process and process.poll() is None:
                print(f"Terminating process: {process_key}")
                terminate_process_gracefully(process, timeout=5)
            del active_processes[process_key]
        except Exception as e:
            print(f"Error cleaning up process {process_key}: {e}")

    # Clean up any remaining connector processes
    cleanup_connector_processes()
    print("Process cleanup completed")

# Register cleanup function to run on server shutdown
atexit.register(cleanup_all_processes)

def classify_error_type(log_content: str, is_first_run: bool = False) -> dict:
    """
    Classify error type based on log content.

    Only detects obvious INFRA issues (JVM/SDK internal errors, network issues).
    For other errors:
    - If first run (never succeeded), likely config/credentials issue
    - Otherwise, ask user if they want auto-fix

    Args:
        log_content: The error log content
        is_first_run: True if the connector has never run successfully (no .run_success marker)
    """
    log_lower = log_content.lower()

    # Infrastructure/SDK error patterns - obvious issues outside the connector code
    infra_error_patterns = [
        # Java/JVM crashes
        "java.lang.", "jvm", "java runtime", "could not find or load main class",
        # gRPC/SDK internal failures
        "grpc", "port=50051",
        # SDK internal file errors (not user code)
        "fivetran_connector_sdk/__init__.py", "connector_helper.py",
        "sdk_connector_tester",
        # Network/connectivity issues (infrastructure, not code)
        "connection refused", "connection timed out", "network unreachable",
        "unable to connect", "could not connect", "connection error",
        "dns resolution", "name resolution", "host not found",
        "ssl", "certificate verify failed", "handshake failed"
    ]

    # Check for obvious infrastructure issues
    for pattern in infra_error_patterns:
        if pattern in log_lower:
            # If first run, also mention credentials as a possible cause
            if is_first_run:
                return {
                    "type": "INFRA",
                    "category": "Infrastructure Issue",
                    "message": "This appears to be a network or connectivity issue.",
                    "guidance": "Please check your network connectivity and try again. Since this connector has not run successfully yet, this could also be a credentials or configuration issue - verify your API keys, usernames, and endpoints are correct."
                }
            else:
                return {
                    "type": "INFRA",
                    "category": "Infrastructure Issue",
                    "message": "This appears to be an infrastructure or network issue, not a connector code problem.",
                    "guidance": "Please check your network connectivity and try again. If the issue persists, verify the API endpoint is reachable."
                }

    # For non-INFRA errors, check if this is a first run
    if is_first_run:
        # First run failure - likely config/credentials issue
        return {
            "type": "FIRST_RUN",
            "category": "First Run Issue",
            "message": "This connector has not run successfully yet. This is likely a configuration or credentials issue.",
            "guidance": "Please verify your configuration values are correct (API keys, usernames, endpoints, etc.)."
        }

    # Has run successfully before - ask user if they want auto-fix
    return {
        "type": "CODE",
        "category": "Possible Code Issue",
        "message": "This may be a code issue that can be automatically fixed.",
        "guidance": "Would you like the AI to attempt to fix this issue?"
    }

# Session persistence file
SESSIONS_FILE = Path(__file__).parent / "sessions.json"

def save_sessions():
    """Save sessions to disk"""
    try:
        # Convert sessions to JSON-serializable format
        sessions_data = {}
        for token, session in active_sessions.items():
            sessions_data[token] = {
                'username': session.username,
                'session_token': session.session_token,
                'created_at': session.created_at.isoformat(),
                'expires_at': session.expires_at.isoformat()
            }

        with open(SESSIONS_FILE, 'w') as f:
            json.dump(sessions_data, f)
    except Exception as e:
        print(f"Error saving sessions: {e}")

def load_sessions():
    """Load sessions from disk"""
    global active_sessions
    try:
        if SESSIONS_FILE.exists():
            with open(SESSIONS_FILE, 'r') as f:
                sessions_data = json.load(f)

            # Convert back to UserSession objects
            active_sessions = {}
            current_time = datetime.now()

            for token, data in sessions_data.items():
                expires_at = datetime.fromisoformat(data['expires_at'])
                # Only load non-expired sessions
                if current_time <= expires_at:
                    session = UserSession(
                        username=data['username'],
                        session_token=data['session_token'],
                        created_at=datetime.fromisoformat(data['created_at']),
                        expires_at=expires_at
                    )
                    active_sessions[token] = session

            print(f"Loaded {len(active_sessions)} active sessions from disk")
        else:
            print("No existing sessions file found, starting with empty sessions")
    except Exception as e:
        print(f"Error loading sessions: {e}")
        active_sessions = {}

# Load sessions on startup - moved to after UserSession class definition

# Constants
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_FILE_EXTENSIONS = {'.py', '.json', '.txt', '.md', '.yaml', '.yml'}
# Original pattern for file names (allows dots, uppercase, spaces, etc.)
ALLOWED_FILENAME_PATTERN = re.compile(r'^[a-zA-Z0-9._/ -]+$')
# Strict pattern for project names only (lowercase, numbers, underscores, must start with letter/underscore)
ALLOWED_PROJECT_NAME_PATTERN = re.compile(r'^[a-z_][a-z0-9_]*$')

# Helper functions
def validate_filename(filename: str) -> bool:
    """Validate filename for security"""
    if not filename or len(filename) > 255:
        return False
    if not ALLOWED_FILENAME_PATTERN.match(filename):
        return False
    if filename.startswith('.') or filename.endswith('.'):
        return False
    return True

def validate_project_name(project_name: str) -> bool:
    """Validate project name with strict rules (lowercase, numbers, underscores only)"""
    if not project_name or len(project_name) > 255:
        return False
    if not ALLOWED_PROJECT_NAME_PATTERN.match(project_name):
        return False
    if project_name.startswith('.') or project_name.endswith('.'):
        return False
    return True

def sanitize_path(path: str) -> str:
    """Sanitize file path to prevent directory traversal"""
    # Remove any path traversal attempts
    path = path.replace('..', '').replace('//', '/')
    # Remove leading slashes
    path = path.lstrip('/')
    return path

def create_error_response(message: str, status_code: int = 400) -> dict:
    """Create standardized error response"""
    return {
        "success": False,
        "error": message,
        "timestamp": datetime.now().isoformat()
    }

def create_success_response(data: dict = None, message: str = "Success") -> dict:
    """Create standardized success response"""
    response = {
        "success": True,
        "message": message,
        "timestamp": datetime.now().isoformat()
    }
    if data:
        response.update(data)
    return response

class GoogleLoginRequest(BaseModel):
    credential: str  # JWT token from Google

class SessionResponse(BaseModel):
    session_token: str
    username: str
    expires_at: str

class UserSession(BaseModel):
    username: str
    session_token: str
    created_at: datetime
    expires_at: datetime
    is_active: bool = True

# Load sessions on startup
load_sessions()

class GenerateConnectorRequest(BaseModel):
    project_name: str


def get_project_data(username: str, project_name: str) -> Optional[dict]:
    """Read project data from JSON file"""
    project_file = BASE_DIR / username / "projects" / f"{project_name}.json"
    if project_file.exists():
        try:
            with open(project_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading project file {project_file}: {e}")
    return None

# Authentication functions
def validate_username(username: str) -> bool:
    """Validate username to prevent path traversal attacks.

    Usernames must only contain lowercase letters, numbers, and underscores.
    This prevents directory traversal attacks like '../admin' or 'user/../../etc'.
    """
    import re
    return bool(re.match(r'^[a-z0-9_]+$', username))


def ensure_workspace_exists(username: str) -> None:
    """Auto-create workspace directories for new users"""
    if not validate_username(username):
        raise ValueError(f"Invalid username format: {username}")
    workspace_base = Path(__file__).parent.parent / "workspaces" / username
    workspace_base.mkdir(parents=True, exist_ok=True)
    (workspace_base / "connectors").mkdir(exist_ok=True)
    (workspace_base / "projects").mkdir(exist_ok=True)
    logger.info(f"Workspace created: {username}")

def email_to_username(email: str) -> str:
    """Convert email to username (john.doe@fivetran.com -> john_doe)"""
    local_part = email.split('@')[0].lower()
    local_part = local_part.split('+')[0]  # Remove +alias
    return local_part.replace('.', '_')

def create_session(username: str) -> str:
    """Create a new session for the user"""
    session_token = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(hours=SESSION_EXPIRE_HOURS)

    session = UserSession(
        username=username,
        session_token=session_token,
        created_at=datetime.now(),
        expires_at=expires_at
    )

    active_sessions[session_token] = session
    save_sessions()  # Persist session to disk
    return session_token

def get_session(session_token: str) -> Optional[UserSession]:
    """Get session by token"""
    if session_token not in active_sessions:
        return None

    session = active_sessions[session_token]

    # Check if session is expired
    if datetime.now() > session.expires_at:
        del active_sessions[session_token]
        return None

    return session

def invalidate_session(session_token: str):
    """Invalidate a session"""
    if session_token in active_sessions:
        del active_sessions[session_token]
        save_sessions()  # Persist session removal to disk

async def get_current_user(request: Request):
    """Get current user from session cookie"""
    session_token = request.cookies.get("session_token")
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    session = get_session(session_token)

    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session",
        )

    # Ensure workspace directories exist (handles case where directories were deleted manually)
    ensure_workspace_exists(session.username)

    return session


# Use environment variable to determine production mode (more reliable than hostname check)
IS_PRODUCTION = os.getenv("PRODUCTION", "false").lower() == "true"

def _is_localhost(request: Request) -> bool:
    """Check if running in development mode (for Secure cookie flag).

    Uses PRODUCTION env var instead of hostname to prevent header manipulation.
    """
    if IS_PRODUCTION:
        return False  # Always use Secure cookies in production
    # In development, check localhost
    return request.url.hostname in ("localhost", "127.0.0.1")


def _set_session_cookie(response: JSONResponse, session_token: str, request: Request) -> None:
    """Set the HttpOnly session cookie on a response."""
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=not _is_localhost(request),
        samesite="lax",
        path="/",
        max_age=SESSION_EXPIRE_HOURS * 3600,
    )

# Authentication endpoints
@app.post("/auth/login")
@limiter.limit("10/minute")
async def login(request: Request, login_request: GoogleLoginRequest):
    """Google OAuth login - domain-based whitelist (rate limited: 10/min)"""
    try:
        # Verify Google JWT token
        idinfo = id_token.verify_oauth2_token(
            login_request.credential,
            google_requests.Request(),
            GOOGLE_CLIENT_ID
        )

        # Extract email and verify it's verified
        google_email = idinfo['email']

        # Ensure email is verified (security)
        if not idinfo.get('email_verified', False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email address not verified"
            )

        # Check domain whitelist
        email_domain = google_email.split('@')[1]
        if email_domain not in ALLOWED_DOMAINS_LIST:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Domain @{email_domain} not authorized"
            )

        # Generate username
        username = email_to_username(google_email)

        # Create workspace
        ensure_workspace_exists(username)

        # Create session
        session_token = create_session(username)
        session = get_session(session_token)

        logger.info(f"Google login: {google_email} -> {username}")

        response = JSONResponse(content={
            "success": True,
            "message": "Login successful",
            "username": username,
            "expires_at": session.expires_at.isoformat()
        })
        _set_session_cookie(response, session_token, request)
        return response

    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google token"
        )

@app.post("/auth/refresh")
@limiter.limit("30/minute")
async def refresh_session(request: Request, current_user: UserSession = Depends(get_current_user)):
    """Refresh session - extends expiration time (rate limited: 30/min)"""
    # Extend the session expiration time
    new_expires_at = datetime.now() + timedelta(hours=SESSION_EXPIRE_HOURS)
    current_user.expires_at = new_expires_at

    # Update the session in storage
    active_sessions[current_user.session_token] = current_user
    save_sessions()  # Persist refreshed session to disk

    response = JSONResponse(content={
        "success": True,
        "message": "Session refreshed successfully",
        "expires_at": new_expires_at.isoformat()
    })
    _set_session_cookie(response, current_user.session_token, request)
    return response

@app.post("/auth/logout")
async def logout(request: Request, current_user: UserSession = Depends(get_current_user)):
    """Logout endpoint - invalidates current session"""
    invalidate_session(current_user.session_token)

    response = JSONResponse(content={"message": "Logged out successfully"})
    response.delete_cookie(
        key="session_token",
        path="/",
        httponly=True,
        secure=not _is_localhost(request),
        samesite="lax",
    )
    return response


@app.get("/auth/check")
async def check_auth(current_user: UserSession = Depends(get_current_user)):
    """Check if current session cookie is valid"""
    return {
        "authenticated": True,
        "username": current_user.username,
        "expires_at": current_user.expires_at.isoformat()
    }


@app.get("/auth/config")
async def get_auth_config():
    """Return public auth configuration (Google Client ID) for the frontend."""
    return {"google_client_id": GOOGLE_CLIENT_ID or ""}



class ProjectRequest(BaseModel):
    username: str
    project_name: str
    description: str

    @validator('project_name')
    def validate_project_name_format(cls, v):
        if not v or not v.strip():
            raise ValueError('Project name is required')
        v = v.strip()
        if len(v) > 255:
            raise ValueError('Project name must be 255 characters or less')
        if not ALLOWED_PROJECT_NAME_PATTERN.match(v):
            raise ValueError('Project name must be lowercase letters, numbers, and underscores only, starting with a letter or underscore')
        return v
    
    @validator('description')
    def validate_description(cls, v):
        if not v or not v.strip():
            raise ValueError('Project description is required')
        return v.strip()


class ConnectorChatRequest(BaseModel):
    username: str
    connector_name: str
    message: str

class FixConnectorRequest(BaseModel):
    project_name: str
    error_logs: dict

    @validator('project_name')
    def validate_project_name_format(cls, v):
        if not v or not ALLOWED_PROJECT_NAME_PATTERN.match(v):
            raise ValueError('Invalid project name format')
        return v


class SmartConnectorRequest(BaseModel):
    """
    Request model for intelligent connector interaction with automatic intent routing.
    
    This model enables natural language interaction where the system automatically
    determines whether the user wants to analyze (understand) or revise (modify)
    their connector based on the message content. Uses AI-powered intent classification
    to route requests to the appropriate agent (ANALYSIS_AGENT or REVISER_AGENT).
    
    Attributes:
        project_name (str): Name of the connector project to interact with.
                           Must match an existing project in the user's workspace.
        user_message (str): Natural language message describing what the user wants.
                           Can be questions (routes to analysis) or modification requests
                           (routes to revision). The system intelligently classifies intent.
    
    Intent Classification:
        - ANALYZE: Questions, explanations, understanding requests
          Keywords: how, what, why, explain, describe, show, help understand
          Example: "How does authentication work in this connector?"
        
        - REVISE: Modifications, fixes, improvements, feature additions  
          Keywords: fix, add, update, change, modify, implement, create
          Example: "Add retry logic to handle API rate limits"
    
    Examples:
        >>> # Analysis request (auto-routed to ANALYSIS_AGENT)
        >>> request = SmartConnectorRequest(
        ...     project_name="salesforce_connector",
        ...     user_message="Explain how the data extraction process works"
        ... )
        
        >>> # Revision request (auto-routed to REVISER_AGENT)
        >>> request = SmartConnectorRequest(
        ...     project_name="my_api_connector",
        ...     user_message="Fix the authentication error and add proper error handling"
        ... )
    """
    project_name: str
    user_message: str

    @validator('project_name')
    def validate_project_name_format(cls, v):
        if not v or not ALLOWED_PROJECT_NAME_PATTERN.match(v):
            raise ValueError('Invalid project name format')
        return v

class DebugConnectorRequest(BaseModel):
    project_name: str
    trigger_context: Optional[str] = "manual"  # "manual" (user clicked debug) or "generation" (called during generation/revise)

    @validator('project_name')
    def validate_project_name_format(cls, v):
        if not v or not ALLOWED_PROJECT_NAME_PATTERN.match(v):
            raise ValueError('Invalid project name format')
        return v

class TriggerAIFixRequest(BaseModel):
    project_name: str
    log_content: str  # Debug logs to pass to AI fixer

    @validator('project_name')
    def validate_project_name_format(cls, v):
        if not v or not ALLOWED_PROJECT_NAME_PATTERN.match(v):
            raise ValueError('Invalid project name format')
        return v

class ValidateDescriptionRequest(BaseModel):
    project_name: str
    description: str
    user_response: Optional[str] = None  # For continuing validation conversations
    conversation_history: Optional[List[Dict[str, str]]] = None  # Previous user/assistant messages for context

    @validator('project_name')
    def validate_project_name_format(cls, v):
        if not v or not ALLOWED_PROJECT_NAME_PATTERN.match(v):
            raise ValueError('Invalid project name format')
        return v

class ValidateDescriptionContinueRequest(BaseModel):
    project_name: str
    user_response: str

    @validator('project_name')
    def validate_project_name_format(cls, v):
        if not v or not ALLOWED_PROJECT_NAME_PATTERN.match(v):
            raise ValueError('Invalid project name format')
        return v

class SubmitConfigRequest(BaseModel):
    project_name: str
    configuration: dict  # Full configuration with actual values
    sensitive_fields: List[str]  # List of field names marked as sensitive

    @validator('project_name')
    def validate_project_name_format(cls, v):
        if not v or not ALLOWED_PROJECT_NAME_PATTERN.match(v):
            raise ValueError('Invalid project name format')
        return v


# --- Workspace management ---
# BASE_DIR is imported from config


def get_user_workspace(username: str) -> dict:
    """Get workspace paths for a user. Does NOT create directories.

    Directory creation should only happen via ensure_workspace_exists()
    which is called after proper authentication during login.
    """
    if not validate_username(username):
        raise ValueError(f"Invalid username format: {username}")
    user_dir = BASE_DIR / username
    structure = {
        "base": user_dir,
        "connectors": user_dir / "connectors",
        "projects": user_dir / "projects",
    }
    # Only return paths, do NOT create directories here
    # This prevents unauthenticated requests from creating user directories
    return {key: str(value) for key, value in structure.items()}


def save_project_data(username: str, project_id: str, project_data: dict):
    """Save project data to user's workspace"""
    user_dir = BASE_DIR / username / "projects"
    user_dir.mkdir(parents=True, exist_ok=True)  # Ensure projects directory exists
    project_file = user_dir / f"{project_data['project_name']}.json"
    with open(project_file, 'w') as f:
        json.dump(project_data, f, indent=2)

    # Create project directory under connectors (but don't create files)
    project_dir = BASE_DIR / username / "connectors" / project_data["project_name"].replace(" ", "_").lower()
    project_dir.mkdir(parents=True, exist_ok=True)

    # Create project state directory for chat history and other state files
    project_state_dir = BASE_DIR / username / "projects" / project_data["project_name"].replace(" ", "_").lower()
    project_state_dir.mkdir(parents=True, exist_ok=True)

    # Create empty chat history file in project state directory only if it doesn't exist
    chat_history_path = project_state_dir / "chat_history.json"
    if not chat_history_path.exists():
        with open(chat_history_path, 'w') as f:
            json.dump([], f, indent=2)

    # Don't create initial files - let the backend job create them as needed


def save_connector_chat_message(username: str, connector_name: str, message: dict, update_last_ai_message: bool = False):
    """Save chat message to connector history"""
    user_workspace = get_user_workspace(username)
    # Store chat history in projects/{name}/ folder (not connectors/)
    project_state_dir = Path(user_workspace["projects"]) / connector_name
    chat_file = project_state_dir / "chat_history.json"

    # Ensure directory exists
    project_state_dir.mkdir(parents=True, exist_ok=True)

    # Load existing messages or create new list
    messages = []
    if chat_file.exists():
        try:
            with open(chat_file, 'r') as f:
                content = f.read().strip()
                if content and content != '[]' and content != '{}':  # Only parse if file has meaningful content
                    messages = json.loads(content)
                else:
                    messages = []
        except (json.JSONDecodeError, ValueError, FileNotFoundError):
            # If file is corrupted, empty, or doesn't exist, start with empty list
            messages = []

    # If updating last AI message, replace the last AI message instead of adding new one
    if update_last_ai_message and messages and messages[-1].get("type") == "ai":
        messages[-1] = message
    else:
        # Add new message
        messages.append(message)

    # Save back
    with open(chat_file, 'w') as f:
        json.dump(messages, f, indent=2)

    return messages


@app.post('/create-project')
def create_project(payload: ProjectRequest, current_user: UserSession = Depends(get_current_user)):
    """Create a new project and return project ID"""

    # Check if project already exists 
    connectors = _get_user_connectors_internal(current_user.username)
    project_exists = any(connector.get("project_name") == payload.project_name for connector in connectors)
    
    if project_exists:
        logger.warning(f"Project '{payload.project_name}' already exists for user {current_user.username}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Project '{payload.project_name}' already exists. Please choose a different name."
        )

    project_id = str(uuid.uuid4())
    project_data = {
        "project_id": project_id,
        "project_name": payload.project_name,
        "description": payload.description,
        "created_at": datetime.now().isoformat(),
        "username": current_user.username  # Use authenticated user's username
    }

    save_project_data(current_user.username, project_id, project_data)

    # Don't create initial files - let the backend job create them as needed
    # The frontend will display files from the directory (empty initially)

    return {
        "success": True,
        "project_id": project_id,
        "project_name": payload.project_name,
        "message": "Project created successfully"
    }


def _get_user_connectors_internal(username: str):
    """Internal function to get user's connectors without FastAPI dependencies"""
    try:
        user_workspace = get_user_workspace(username)
        projects_dir = Path(user_workspace["projects"])

        connectors = []

        # Get all connectors from projects directory (both generated and uploaded)
        if projects_dir.exists():
            for project_file in projects_dir.iterdir():
                if project_file.is_file() and project_file.suffix == '.json':
                    try:
                        with open(project_file, 'r') as f:
                            project_data = json.load(f)

                        # Extract connector information from project metadata
                        connectors.append({
                            "project_name": project_data.get("project_name", ""),
                            "display_name": project_data.get("project_name", ""),
                            "description": project_data.get("description", ""),
                            "version": "1.0.0",  # Default version since it's not stored in project metadata
                            "created_at": project_data.get("created_at", ""),
                            "project_id": project_data.get("project_id", ""),
                            "type": project_data.get("type", "generated"),  # "generated" or "uploaded"
                            "connector_path": project_data.get("connector_path", f"connectors/{project_data.get('project_name')}")
                        })
                    except Exception as e:
                        # Skip corrupted project files
                        print(f"Error reading project file {project_file}: {e}")
                        continue

        # Sort connectors by creation date (newest first)
        connectors.sort(key=lambda x: x.get("created_at", ""), reverse=True)

        return connectors
    except Exception as e:
        print(f"Error getting user connectors: {e}")
        return []

@app.get('/user-connectors/{username}')
def get_user_connectors(username: str, current_user: UserSession = Depends(get_current_user)):
    """Get list of user's connectors from projects directory (unified JSON approach)"""
    # Ensure user can only access their own data
    if username != current_user.username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You can only access your own data"
        )

    try:
        connectors = _get_user_connectors_internal(username)

        # Convert to the expected API format
        api_connectors = []
        for connector in connectors:
            api_connectors.append({
                "name": connector.get("project_name", ""),
                "display_name": connector.get("project_name", ""),
                "description": connector.get("description", ""),
                "version": connector.get("version", "1.0.0"),
                "created_at": connector.get("created_at", ""),
                "project_id": connector.get("project_id", ""),
                "type": connector.get("type", "generated")
            })

        return {"success": True, "connectors": api_connectors}
    except Exception as e:
        logger.error(f"Error listing connectors for user {username}: {str(e)}")
        return {"success": False, "message": "Failed to load connectors. Please try again."}


@app.get('/check-project-exists/{username}/{project_name}')
def check_project_exists(username: str, project_name: str, current_user: UserSession = Depends(get_current_user)):
    """Check if a project with the given name already exists for the user"""
    # Ensure user can only access their own data
    if username != current_user.username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You can only access your own data"
        )
    
    # Validate and sanitize project name
    if not validate_project_name(project_name):
        return {
            "success": False,
            "message": "Invalid project name. Must start with a letter or underscore, and can only contain lowercase letters, numbers, and underscores"
        }

    project_name = sanitize_path(project_name)

    try:
        # Check if project exists by looking in the projects directory
        connectors = _get_user_connectors_internal(username)
        exists = any(connector.get("project_name") == project_name for connector in connectors)

        return {
            "success": True,
            "exists": exists,
            "project_name": project_name
        }
    except Exception as e:
        logger.error(f"Error checking project existence for user {username}: {str(e)}")
        return {"success": False, "message": "An error occurred while checking project existence."}


@app.get('/project-data/{username}/{project_name}')
def get_project_data_endpoint(username: str, project_name: str, current_user: UserSession = Depends(get_current_user)):
    """Get project metadata including description"""
    # Ensure user can only access their own data
    if username != current_user.username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You can only access your own data"
        )

    # Validate project name
    if not ALLOWED_PROJECT_NAME_PATTERN.match(project_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid project name format"
        )

    project_name = sanitize_path(project_name)

    try:
        project_data = get_project_data(username, project_name)
        if project_data:
            return {
                "success": True,
                "project": project_data
            }
        else:
            return {
                "success": False,
                "message": "Project not found"
            }
    except Exception as e:
        logger.error(f"Error getting project data for user {username}: {str(e)}")
        return {"success": False, "message": "An error occurred while getting project data."}


@app.post('/connector-chat')
def connector_chat(payload: ConnectorChatRequest, current_user: UserSession = Depends(get_current_user)):
    """Handle chat messages for connectors and return AI response"""
    # Ensure user can only access their own data
    if payload.username != current_user.username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You can only access your own data"
        )

    # Save user message
    user_message = {
        "type": "user",
        "text": payload.message,
        "timestamp": datetime.now().isoformat()
    }
    save_connector_chat_message(payload.username, payload.connector_name, user_message)

    # Generate AI response based on message content
    ai_response = ""

    # Save AI response
    ai_message = {
        "type": "ai",
        "text": ai_response,
        "timestamp": datetime.now().isoformat(),
        "responseTime": 2  # Approximate response time for non-streaming
    }
    messages = save_connector_chat_message(payload.username, payload.connector_name, ai_message)

    return {
        "success": True,
        "response": ai_response,
        "messages": messages
    }


@app.get('/connector-chat/{username}/{connector_name}')
def get_connector_chat_history(username: str, connector_name: str, current_user: UserSession = Depends(get_current_user)):
    """Get chat history for a connector"""
    # Ensure user can only access their own data
    if username != current_user.username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You can only access your own data"
        )
    # Validate connector_name to prevent path traversal
    if not ALLOWED_PROJECT_NAME_PATTERN.match(connector_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid connector name format"
        )
    try:
        user_workspace = get_user_workspace(username)
        # Check new location first: projects/{name}/chat_history.json
        project_state_dir = Path(user_workspace["projects"]) / connector_name
        chat_file = project_state_dir / "chat_history.json"

        # Backward compatibility: check old location if new doesn't exist
        if not chat_file.exists():
            old_chat_file = Path(user_workspace["connectors"]) / connector_name / "chat_history.json"
            if old_chat_file.exists():
                chat_file = old_chat_file

        if not chat_file.exists():
            return {"success": True, "messages": []}

        with open(chat_file, 'r') as f:
            content = f.read().strip()
            if content and content != '[]' and content != '{}':
                messages = json.loads(content)
            else:
                messages = []

        return {
            "success": True,
            "messages": messages
        }
    except Exception as e:
        logger.error(f"Error loading chat history for connector: {str(e)}")
        return {"success": False, "message": "Failed to load chat history."}


@app.get('/connector-files/{username}/{connector_name}')
def get_connector_files(username: str, connector_name: str, current_user: UserSession = Depends(get_current_user)):
    """Get list of files in a connector directory (recursively)"""
    # Ensure user can only access their own data
    if username != current_user.username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You can only access your own data"
        )
    # Validate connector_name to prevent path traversal
    if not ALLOWED_PROJECT_NAME_PATTERN.match(connector_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid connector name format"
        )
    try:
        user_workspace = get_user_workspace(username)
        connector_dir = Path(user_workspace["connectors"]) / connector_name

        # Create directory if it doesn't exist (for new projects)
        connector_dir.mkdir(parents=True, exist_ok=True)

        files = []
        # Recursively scan all files in the connector directory
        for file_path in connector_dir.rglob('*'):
            if file_path.is_file():
                # Skip Python cache files and directories, and internal files
                if (file_path.suffix == '.pyc' or
                    '__pycache__' in file_path.parts or
                    'venv' in file_path.parts or
                    file_path.name.endswith('.pyo') or
                    file_path.name.endswith('.wal') or
                    file_path.name == 'chat_history.json' or
                    file_path.name == '.config_metadata.json' or
                    file_path.name == '.config_pipe'):
                    continue
                    
                stat = file_path.stat()
                # Get relative path from connector directory
                relative_path = file_path.relative_to(connector_dir)
                files.append({
                    "name": str(relative_path),  # Use relative path to show subdirectory structure
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat()
                })

        return {"success": True, "files": files}
    except Exception as e:
        logger.error(f"Error loading connector files: {str(e)}")
        return {"success": False, "message": "Failed to load connector files."}


@app.get('/connector-generation-status/{username}/{connector_name}')
def get_connector_generation_status(username: str, connector_name: str, current_user: UserSession = Depends(get_current_user)):
    """Check if connector generation has been completed successfully."""
    # Ensure user can only access their own data
    if username != current_user.username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You can only access your own data"
        )
    # Validate connector_name to prevent path traversal
    if not ALLOWED_PROJECT_NAME_PATTERN.match(connector_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid connector name format"
        )
    try:
        user_workspace = get_user_workspace(username)
        connector_dir = Path(user_workspace["connectors"]) / connector_name
        project_state_dir = Path(user_workspace["projects"]) / connector_name

        if not connector_dir.exists():
            return {"success": True, "generation_complete": False, "reason": "connector_not_found"}

        # Check for marker in projects/{name}/ (new location)
        marker_file = project_state_dir / ".generation_complete"
        # Also check old location for backward compatibility
        old_marker_file = connector_dir / ".generation_complete"
        connector_file = connector_dir / "connector.py"

        if marker_file.exists():
            # Read completion timestamp from new location
            completed_at = marker_file.read_text().strip()
            return {
                "success": True,
                "generation_complete": True,
                "completed_at": completed_at
            }
        elif old_marker_file.exists():
            # Read completion timestamp from old location (backward compatibility)
            completed_at = old_marker_file.read_text().strip()
            return {
                "success": True,
                "generation_complete": True,
                "completed_at": completed_at
            }
        elif connector_file.exists():
            # connector.py exists but no marker - interrupted generation
            return {
                "success": True,
                "generation_complete": False,
                "reason": "interrupted",
                "has_partial_files": True
            }
        else:
            # No connector.py at all - never generated
            return {
                "success": True,
                "generation_complete": False,
                "reason": "not_started"
            }
    except Exception as e:
        logger.error(f"Error checking generation status: {str(e)}")
        return {"success": False, "message": "Failed to check generation status."}


@app.get('/connector-file/{username}/{connector_name}/{filename:path}')
def get_connector_file_content(username: str, connector_name: str, filename: str, current_user: UserSession = Depends(get_current_user)):
    """Get content of a specific connector file (supports subdirectories)"""
    # Ensure user can only access their own data
    if username != current_user.username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You can only access your own data"
        )
    # Validate connector_name to prevent path traversal
    if not ALLOWED_PROJECT_NAME_PATTERN.match(connector_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid connector name format"
        )
    try:
        user_workspace = get_user_workspace(username)
        connector_dir = Path(user_workspace["connectors"]) / connector_name

        if not connector_dir.exists():
            return {"success": False, "message": "Connector directory not found"}

        # Handle files in subdirectories by joining the filename path
        file_path = connector_dir / filename
        if not file_path.exists():
            return {"success": False, "message": "File not found"}

        # Security check: ensure the file is within the connector directory
        try:
            file_path.resolve().relative_to(connector_dir.resolve())
        except ValueError:
            return {"success": False, "message": "Access denied: file outside connector directory"}

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Special handling for configuration.json: decrypt and mask sensitive values
        if filename == 'configuration.json' and content.startswith('ENCRYPTED:'):
            try:
                from encryption import decrypt_config
                config = decrypt_config(current_user.username, content)

                # Read sensitive fields metadata
                metadata_file = connector_dir / ".config_metadata.json"
                sensitive_fields = set()
                if metadata_file.exists():
                    try:
                        with open(metadata_file) as f:
                            metadata = json.load(f)
                            sensitive_fields = set(metadata.get("sensitive_fields", []))
                    except Exception:
                        pass

                # Mask sensitive values
                masked_config = {}
                for key, value in config.items():
                    if key in sensitive_fields and value:
                        masked_config[key] = "****"
                    else:
                        masked_config[key] = value

                # Return masked JSON as content
                content = json.dumps(masked_config, indent=2)
            except Exception as decrypt_error:
                # Can't decrypt - return a flag so frontend can show warning
                logger.warning(f"Cannot decrypt configuration.json for display: {decrypt_error}")
                return {
                    "success": True,
                    "content": "",
                    "decrypt_failed": True,
                    "message": "Configuration was encrypted by a different user or system."
                }

        return {"success": True, "content": content}
    except Exception as e:
        logger.error(f"Error loading file content: {str(e)}")
        return {"success": False, "message": "Failed to load file content."}

@app.post('/reset-project/{username}/{connector_name}')
def reset_project(username: str, connector_name: str, delete_venv: bool = False, current_user: UserSession = Depends(get_current_user)):
    """Reset project by deleting the files subdirectory and optionally the virtual environment"""
    # Ensure user can only access their own data
    if username != current_user.username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You can only access your own data"
        )
    # Validate connector_name to prevent path traversal
    if not ALLOWED_PROJECT_NAME_PATTERN.match(connector_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid connector name format"
        )
    try:
        user_workspace = get_user_workspace(username)
        project_metadata = next((p for p in _get_user_connectors_internal(username) if p.get('project_name') == connector_name), None)

        if not project_metadata:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Connector '{connector_name}' not found for user '{username}'"
            )

        connector_path = Path(user_workspace["base"]) / project_metadata['connector_path']
        files_dir = connector_path / "files"
        venv_dir = connector_path / "venv"

        deleted_items = []

        # Delete files directory
        if files_dir.exists():
            import shutil
            shutil.rmtree(files_dir)
            deleted_items.append("files directory")
            logger.info(f"Reset project {connector_name} for user {username} - deleted files directory")

        # Delete venv directory only if requested
        if delete_venv and venv_dir.exists():
            import shutil
            shutil.rmtree(venv_dir)
            deleted_items.append("virtual environment")
            logger.info(f"Reset project {connector_name} for user {username} - deleted venv directory")

        if deleted_items:
            return {
                "message": f"Project reset successfully: deleted {', '.join(deleted_items)}",
                "deleted": deleted_items
            }
        else:
            logger.info(f"Reset project {connector_name} for user {username} - no directories to reset")
            return {
                "message": "No directories to reset",
                "deleted": []
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resetting project {connector_name} for user {username}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset project: {e}"
        )

@app.get('/download-project/{username}/{connector_name}')
def download_project(username: str, connector_name: str, current_user: UserSession = Depends(get_current_user)):
    """Download all files in a connector project as a zip file"""
    # Ensure user can only access their own data
    if username != current_user.username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You can only access your own data"
        )
    # Validate connector_name to prevent path traversal
    if not ALLOWED_PROJECT_NAME_PATTERN.match(connector_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid connector name format"
        )

    try:
        user_workspace = get_user_workspace(username)
        connector_dir = Path(user_workspace["connectors"]) / connector_name

        if not connector_dir.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Connector directory not found"
            )

        # Create a zip file in memory
        zip_buffer = io.BytesIO()

        # Define directories and files to exclude from download
        excluded_dirs = {'venv', '__pycache__'}
        excluded_files = {'.config_pipe', '.DS_Store', 'session_metadata.json', '.config_metadata.json', '.run_success'}

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Walk through all files in the connector directory
            for root, dirs, files in os.walk(connector_dir):
                # Remove excluded directories from dirs list (modifies in-place to prevent descent)
                dirs[:] = [d for d in dirs if d not in excluded_dirs]

                for file in files:
                    # Skip excluded files
                    if file in excluded_files:
                        continue

                    file_path = Path(root) / file
                    # Calculate relative path from connector directory
                    arcname = file_path.relative_to(connector_dir)

                    # Special handling for configuration.json: decrypt before adding to zip
                    if file == 'configuration.json':
                        try:
                            content = file_path.read_text()
                            if content.startswith('ENCRYPTED:'):
                                from encryption import decrypt_config
                                try:
                                    config = decrypt_config(current_user.username, content)
                                    # Add decrypted JSON to zip
                                    zip_file.writestr(str(arcname), json.dumps(config, indent=2))
                                    continue
                                except Exception as decrypt_error:
                                    # Can't decrypt - skip this file (don't include encrypted config)
                                    logger.warning(f"Skipping encrypted config in download (cannot decrypt): {decrypt_error}")
                                    continue
                        except Exception as e:
                            logger.warning(f"Error reading configuration.json: {e}")

                    # Add file to zip
                    zip_file.write(file_path, arcname)

        # Reset buffer position to beginning
        zip_buffer.seek(0)

        # Return the zip file as a streaming response
        return StreamingResponse(
            io.BytesIO(zip_buffer.getvalue()),
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={connector_name}.zip"}
        )

    except Exception as e:
        logger.error(f"Error creating zip file for {username}/{connector_name}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating zip file. Please try again."
        )

@app.delete('/delete-file')
def delete_file(request: dict, current_user: UserSession = Depends(get_current_user)):
    """Delete a file from a connector directory"""
    try:
        # Extract parameters
        filename = request.get('filename', '').strip()
        project_name = request.get('project_name', '').strip()
        
        if not filename:
            raise HTTPException(status_code=400, detail="Filename is required")
        if not project_name:
            raise HTTPException(status_code=400, detail="Project name is required")

        # Security validation - validate project name to prevent directory traversal
        if not validate_project_name(project_name):
            raise HTTPException(status_code=400, detail="Invalid project name")

        # Security validation - prevent directory traversal in filename
        if '..' in filename or filename.startswith('/') or '\\' in filename:
            raise HTTPException(status_code=400, detail="Invalid filename")
        
        # Prevent deletion of critical files
        critical_files = ['connector.py', 'configuration.json']
        base_filename = filename.split('/')[-1]  # Get filename without directory
        if base_filename in critical_files:
            raise HTTPException(status_code=400, detail=f"Cannot delete critical file: {base_filename}")
        
        # Get user workspace and construct file path
        user_workspace = get_user_workspace(current_user.username)
        project_dir = Path(user_workspace["connectors"]) / project_name
        file_path = project_dir / filename
        
        # Ensure file exists
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        
        # Ensure file is within user's project directory (security check)
        try:
            file_path.resolve().relative_to(project_dir.resolve())
        except ValueError:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Delete the file
        file_path.unlink()
        
        logger.info(f"File deleted: {filename} from project {project_name} by user {current_user.username}")
        
        return {
            "success": True,
            "message": f"File '{filename}' deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = log_and_format_error(e, "Error deleting file")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg
        )


@app.delete('/delete-connector')
def delete_connector(request: dict, current_user: UserSession = Depends(get_current_user)):
    """Delete an entire connector including code directory and project metadata"""
    try:
        connector_name = request.get('connector_name', '').strip()

        if not connector_name:
            raise HTTPException(status_code=400, detail="Connector name is required")

        # Security validation - prevent directory traversal
        if '..' in connector_name or '/' in connector_name or '\\' in connector_name:
            raise HTTPException(status_code=400, detail="Invalid connector name")

        # Get user workspace paths
        user_workspace = get_user_workspace(current_user.username)
        connectors_dir = Path(user_workspace["connectors"])
        projects_dir = Path(user_workspace["projects"])
        connector_dir = connectors_dir / connector_name
        project_file = projects_dir / f"{connector_name}.json"
        project_state_dir = projects_dir / connector_name

        # Check if either the connector directory or project file exists
        connector_exists = connector_dir.exists()
        project_exists = project_file.exists()
        project_state_exists = project_state_dir.exists()

        if not connector_exists and not project_exists and not project_state_exists:
            raise HTTPException(status_code=404, detail="Connector not found")

        # Ensure directory is within user's connectors directory (security check)
        if connector_exists:
            try:
                connector_dir.resolve().relative_to(connectors_dir.resolve())
            except ValueError:
                raise HTTPException(status_code=403, detail="Access denied")

        deleted_items = []

        # Delete the connector code directory
        if connector_exists:
            shutil.rmtree(connector_dir)
            deleted_items.append("code directory")

        # Delete the project metadata file
        if project_exists:
            project_file.unlink()
            deleted_items.append("project metadata")

        # Delete the project state directory (chat history, generation markers, etc.)
        if project_state_exists:
            shutil.rmtree(project_state_dir)
            deleted_items.append("chat history")

        logger.info(f"Connector deleted: {connector_name} ({', '.join(deleted_items)}) by user {current_user.username}")

        return {
            "success": True,
            "message": f"Connector '{connector_name}' deleted successfully",
            "deleted": deleted_items
        }

    except HTTPException:
        raise
    except Exception as e:
        error_msg = log_and_format_error(e, "Error deleting connector")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg
        )

@app.post('/save-file')
def save_file(request: dict, current_user: UserSession = Depends(get_current_user)):
    """Save content to a file in a connector directory"""
    try:
        # Extract and validate required fields
        username = request.get('username')
        project_name = request.get('project_name')
        filename = request.get('filename')
        content = request.get('content')

        # Validate required fields
        if not username or not project_name or not filename or content is None:
            logger.warning(f"Missing required fields for save-file request from user {current_user.username}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing required fields: username, project_name, filename, content"
            )

        # Ensure user can only access their own data
        if username != current_user.username:
            logger.warning(f"User {current_user.username} attempted to access data for {username}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You can only access your own data"
            )

        # Validate filename for security
        if not validate_filename(filename):
            logger.warning(f"Invalid filename '{filename}' from user {current_user.username}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid filename. Only alphanumeric characters, dots, underscores, and hyphens are allowed"
            )

        # Validate file extension
        file_ext = Path(filename).suffix.lower()
        if file_ext not in ALLOWED_FILE_EXTENSIONS:
            logger.warning(f"Invalid file extension '{file_ext}' from user {current_user.username}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File extension '{file_ext}' not allowed. Allowed extensions: {', '.join(ALLOWED_FILE_EXTENSIONS)}"
            )

        # Validate content size
        if len(content.encode('utf-8')) > MAX_FILE_SIZE:
            logger.warning(f"File too large ({len(content.encode('utf-8'))} bytes) from user {current_user.username}")
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024*1024)}MB"
            )

        # Sanitize project name and filename
        project_name = sanitize_path(project_name)
        filename = sanitize_path(filename)

        user_workspace = get_user_workspace(username)
        file_path = Path(user_workspace["connectors"]) / project_name / filename

        # Ensure the directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write the content to the file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

        logger.info(f"File saved successfully: {file_path} by user {current_user.username}")
        return create_success_response(
            data={"file_path": str(file_path)},
            message="File saved successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        error_msg = log_and_format_error(e, "Error saving file")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg
        )

@app.post('/upload-connector')
async def upload_connector(files: List[UploadFile] = File(...), username: str = Form(...), project_name: Optional[str] = Form(None), current_user: UserSession = Depends(get_current_user)):
    """Upload connector files to user's workspace"""
    try:
        # Validate username
        if not username:
            logger.warning(f"Missing username in upload request from user {current_user.username}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username is required"
            )

        # Ensure user can only access their own data
        if username != current_user.username:
            logger.warning(f"User {current_user.username} attempted to upload for {username}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You can only access your own data"
            )

        if not files:
            logger.warning(f"No files provided in upload request from user {current_user.username}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No files provided"
            )

        # Validate file count
        if len(files) > 50:  # Reasonable limit
            logger.warning(f"Too many files ({len(files)}) in upload request from user {current_user.username}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Too many files. Maximum 50 files allowed per upload"
            )

        # Get user workspace
        user_workspace = get_user_workspace(username)
        connectors_dir = Path(user_workspace["connectors"])
        projects_dir = Path(user_workspace["projects"])

        # Determine connector name: prioritize user-provided name, then extract from files, then use timestamp
        connector_name = None
        
        if project_name and project_name.strip():
            # Use user-provided project name (validate and sanitize it)
            if not validate_project_name(project_name.strip()):
                logger.warning(f"Invalid project name '{project_name}' from user {current_user.username}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid project name. Must start with a letter or underscore, and can only contain lowercase letters, numbers, and underscores"
                )
            connector_name = sanitize_path(project_name.strip())
        else:
            # Extract the root directory name from the first file path
            # If files have paths like "hello_project/connector.py", extract "hello_project"
            for file in files:
                if file.filename and '/' in file.filename:
                    # Extract the root directory name
                    connector_name = file.filename.split('/')[0]
                    break

            # If no directory structure found, use timestamp
            if not connector_name:
                connector_name = f"uploaded_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Check if connector with this name already exists in projects
        if project_name and project_name.strip():
            # For user-provided names, enforce uniqueness strictly (don't auto-rename)
            if (projects_dir / f"{connector_name}.json").exists():
                logger.warning(f"Project '{connector_name}' already exists for user {current_user.username}")
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Project '{connector_name}' already exists. Please choose a different name."
                )
        else:
            # For auto-extracted names, allow auto-renaming to avoid conflicts
            original_connector_name = connector_name
            counter = 1
            while (projects_dir / f"{connector_name}.json").exists():
                connector_name = f"{original_connector_name}_{counter}"
                counter += 1

        # Create connector directory in connectors folder
        connector_dir = connectors_dir / connector_name
        connector_dir.mkdir(parents=True, exist_ok=True)

        uploaded_files = []
        total_size = 0

        # Save all uploaded files
        for file in files:
            if not file.filename:
                continue

            # Validate filename
            if not validate_filename(file.filename):
                logger.warning(f"Invalid filename '{file.filename}' from user {current_user.username}")
                continue

            # Sanitize filename and remove root directory prefix if present
            safe_filename = sanitize_path(file.filename)

            # If the file has a directory structure, remove the root directory prefix
            # since we're already using the root directory name as the connector name
            if '/' in safe_filename:
                # Remove the first directory from the path
                path_parts = safe_filename.split('/')
                if len(path_parts) > 1:
                    safe_filename = '/'.join(path_parts[1:])

            file_path = connector_dir / safe_filename
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Read file content
            content = await file.read()

            # Validate file size
            if len(content) > MAX_FILE_SIZE:
                logger.warning(f"File '{file.filename}' too large ({len(content)} bytes) from user {current_user.username}")
                continue

            # Validate file extension
            file_ext = Path(file.filename).suffix.lower()
            if file_ext not in ALLOWED_FILE_EXTENSIONS:
                logger.warning(f"Invalid file extension '{file_ext}' for file '{file.filename}' from user {current_user.username}")
                continue

            # Write file content
            with open(file_path, 'wb') as buffer:
                buffer.write(content)

            uploaded_files.append(safe_filename)
            total_size += len(content)

        if not uploaded_files:
            logger.warning(f"No valid files uploaded by user {current_user.username}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid files uploaded. Check file extensions and names"
            )

        # Create a basic configuration.json if it doesn't exist
        config_path = connector_dir / "configuration.json"
        if not config_path.exists():
            config = {
                "connector_name": connector_name,
                "description": "Uploaded connector",
                "version": "1.0.0",
                "created_at": datetime.now().isoformat(),
                "uploaded": True
            }
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)

        # Encrypt configuration.json for secure storage
        # (whether it was uploaded or just created)
        try:
            config_content = config_path.read_text()
            # Only encrypt if it's not already encrypted
            if not config_content.startswith('ENCRYPTED:'):
                try:
                    config_data = json.loads(config_content)
                    from encryption import encrypt_config
                    encrypted_content = encrypt_config(current_user.username, config_data)
                    config_path.write_text(encrypted_content)

                    # Mark all fields as sensitive by default for uploaded projects
                    # User can change this later via the config editor
                    metadata_file = connector_dir / ".config_metadata.json"
                    all_fields = list(config_data.keys())
                    with open(metadata_file, 'w') as f:
                        json.dump({"sensitive_fields": all_fields}, f, indent=2)

                    logger.info(f"Encrypted configuration.json for uploaded project '{connector_name}' (all {len(all_fields)} fields marked sensitive)")
                except json.JSONDecodeError:
                    logger.warning(f"configuration.json is not valid JSON, skipping encryption for project '{connector_name}'")
        except Exception as e:
            logger.warning(f"Could not encrypt configuration.json for project '{connector_name}': {e}")

        # Create a JSON file in projects directory for unified listing
        project_id = str(uuid.uuid4())
        project_data = {
            "project_id": project_id,
            "project_name": connector_name,
            "description": "Uploaded connector",
            "version": "1.0.0",
            "created_at": datetime.now().isoformat(),
            "type": "uploaded",
            "connector_path": str(connector_dir.relative_to(user_workspace["base"]))
        }

        project_file = projects_dir / f"{connector_name}.json"
        with open(project_file, 'w') as f:
            json.dump(project_data, f, indent=2)

        logger.info(f"Connector uploaded successfully: {connector_name} by user {current_user.username} ({len(uploaded_files)} files, {total_size} bytes)")
        return create_success_response(
            data={
                "connector_name": connector_name,
                "uploaded_files": uploaded_files,
                "total_files": len(uploaded_files),
                "total_size": total_size
            },
            message=f"Connector uploaded successfully as '{connector_name}'"
        )

    except HTTPException:
        raise
    except Exception as e:
        error_msg = log_and_format_error(e, "Error uploading connector")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg
        )


@app.post('/generate-connector-stream')
@limiter.limit("5/minute")
async def generate_connector_stream(request: Request, body: GenerateConnectorRequest, current_user: UserSession = Depends(get_current_user)):
    """Generate a new Fivetran connector using AI with real-time log streaming (rate limited: 5/min)"""
    try:
        # Validate project_name is provided
        if not body.project_name:
            logger.warning(f"Missing project_name in generate request from user {current_user.username}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing required field: project_name"
            )

        # Validate project name format
        if not validate_project_name(body.project_name):
            logger.warning(f"Invalid project name '{body.project_name}' from user {current_user.username}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid project name. Must start with a letter or underscore, and can only contain lowercase letters, numbers, and underscores"
            )

        # Sanitize project name
        project_name = sanitize_path(body.project_name)

        # Read description from project JSON file
        project_data = get_project_data(current_user.username, project_name)
        description = project_data.get("description", "") if project_data else ""
        if not description:
            logger.warning(f"No description found for project '{project_name}' from user {current_user.username}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No description found for project '{project_name}'. Please ensure the project was created with a description."
            )

        # Get user workspace
        user_workspace = get_user_workspace(current_user.username)
        connectors_dir = Path(user_workspace["connectors"])
        projects_dir = Path(user_workspace["projects"])
        project_dir = connectors_dir / project_name
        project_state_dir = projects_dir / project_name

        # Get API key from environment
        api_key = get_anthropic_api_key()
        if not api_key:
            logger.warning(f"No API key provided for generation request from user {current_user.username}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="API key is required. Set CSDKAI_ANTHROPIC_API_KEY or ANTHROPIC_API_KEY environment variable"
            )

        # Ensure directories exist
        project_dir.mkdir(parents=True, exist_ok=True)
        project_state_dir.mkdir(parents=True, exist_ok=True)

        # Remove any existing generation complete marker (in case of re-generation)
        # Check both new and old locations for backward compatibility
        generation_complete_marker = project_state_dir / ".generation_complete"
        old_marker = project_dir / ".generation_complete"
        if generation_complete_marker.exists():
            generation_complete_marker.unlink()
            logger.info(f"Removed existing generation complete marker for regeneration")
        if old_marker.exists():
            old_marker.unlink()
            logger.info(f"Removed old generation complete marker from connectors dir")

        logger.info(f"Starting streaming connector generation for project '{project_name}' by user {current_user.username}")

        async def generate_stream():
            import queue
            import threading
            import subprocess

            try:
                # Stream initial status

                # Prepare arguments for the generation script
                user_workspace_path = Path(user_workspace["base"])
                app_dir = Path(__file__).parent

                # Debug info (only show if generation script doesn't exist)
                script_exists = (app_dir / "_generate.py").exists()
                if not script_exists:
                    yield f"data: {json.dumps({'type': 'log', 'level': 'ERROR', 'message': 'Generation script not found!'})}\n\n"

                # Set environment variables
                env = os.environ.copy()
                env['CSDKAI_ANTHROPIC_API_KEY'] = api_key
                env['PYTHONUNBUFFERED'] = '1'  # Force Python to flush output immediately

                # Create a queue to capture output in real-time
                output_queue = queue.Queue()
                error_queue = queue.Queue()

                def stream_output(pipe, output_queue, prefix=""):
                    """Stream output from subprocess pipe to queue"""
                    try:
                        for line in iter(pipe.readline, ''):
                            if line:
                                line_stripped = line.rstrip()
                                if line_stripped.strip():
                                    output_queue.put(f"{prefix}{line_stripped}")
                    except Exception as e:
                        logger.error(f"Error reading subprocess output: {str(e)}")
                        output_queue.put("Error reading process output")
                    finally:
                        pipe.close()

                # Use virtual environment Python if available
                backend_dir = app_dir.parent
                venv_python = backend_dir / ".venv" / "bin" / "python"
                python_exe = str(venv_python) if venv_python.exists() else sys.executable

                # Use real generation script
                cmd = [
                    python_exe,
                    str(app_dir / "_generate.py"),
                    project_name,
                    description,  # Use description from JSON or request
                    "",  # Empty API key - use environment variable
                    str(user_workspace_path)
                ]

                # Start the generation process with process group for better isolation
                process = subprocess.Popen(cmd,
                                           stdin=subprocess.PIPE,  # Enable stdin for config submission
                                           stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE,
                                           env=env,
                                           cwd=str(app_dir),
                                           text=True,   # Use text mode
                                           bufsize=1,   # Line buffered
                                           universal_newlines=True,
                                           preexec_fn=os.setsid if os.name != 'nt' else None
                                           )

                # Store the process reference for potential termination
                process_key = f"{current_user.username}:{project_name}"
                active_processes[process_key] = process
                
                # Log process lifecycle
                print(f"Started process {process.pid} for {process_key}")

                # Subprocess started

                # Start threads to capture stdout and stderr
                stdout_thread = threading.Thread(
                    target=stream_output,
                    args=(process.stdout, output_queue, "")
                )
                stderr_thread = threading.Thread(
                    target=stream_output,
                    args=(process.stderr, output_queue, "ERROR: ")
                )

                stdout_thread.start()
                stderr_thread.start()

                # Output capture threads started

                # Stream output as it comes
                output_count = 0
                collected_logs = []  # Collect logs for chat history
                initial_ai_message_saved = False  # Track if we've saved initial AI message
                captured_session_id = None  # Capture session ID for in-memory storage
                while True:
                    # Check if process is still running
                    return_code = process.poll()

                    # Get output from queue with non-blocking check
                    try:
                        line = output_queue.get_nowait()  # Non-blocking
                        output_count += 1
                        # Process output line from generation script

                        # Check for CONFIG_REVIEW_REQUIRED message before testing
                        if line.startswith("CONFIG_REVIEW_REQUIRED:"):
                            try:
                                config_data = line.split(":", 1)[1].strip()
                                config_json = json.loads(config_data)

                                # Merge cached credentials into config (pre-fill popup with actual values)
                                credentials_key = f"{current_user.session_token}:{project_name}"
                                merged_config = config_json['configuration'].copy()

                                # Try memory cache for credentials
                                cached_creds = get_credentials_for_project(
                                    current_user.session_token, project_name
                                )

                                if cached_creds:
                                    # Replace "****" with actual cached values for pre-filling
                                    for key, value in merged_config.items():
                                        if value == "****":
                                            if key in cached_creds:
                                                merged_config[key] = cached_creds[key]
                                            else:
                                                # No cached credential - show empty field
                                                merged_config[key] = ""
                                    # Clear memory cache AFTER merging (forces polling to wait for new submission)
                                    with credentials_lock:
                                        if credentials_key in session_credentials:
                                            del session_credentials[credentials_key]
                                else:
                                    # No cached credentials at all - replace "****" with empty strings
                                    for key, value in merged_config.items():
                                        if value == "****":
                                            merged_config[key] = ""

                                # Read sensitivity metadata if it exists
                                metadata_file = project_dir / ".config_metadata.json"
                                sensitive_fields = []
                                if metadata_file.exists():
                                    try:
                                        with open(metadata_file) as f:
                                            metadata = json.load(f)
                                            sensitive_fields = metadata.get("sensitive_fields", [])
                                    except Exception as e:
                                        print(f"Warning: Could not read metadata file: {e}")

                                # Clear any stale cancellation flags before showing popup
                                with cancellation_lock:
                                    if credentials_key in session_cancellations:
                                        del session_cancellations[credentials_key]

                                # Yield config review event with merged values AND sensitive fields
                                config_review_response = {
                                    "type": "config_review",
                                    "configuration": merged_config,
                                    "sensitive_fields": sensitive_fields,
                                    "timestamp": datetime.now().isoformat()
                                }
                                yield f"data: {json.dumps(config_review_response)}\n\n"

                                # Poll for credentials submission (subprocess is blocked on stdin)
                                credentials_provided = False
                                credentials_key = f"{current_user.session_token}:{project_name}"
                                while not credentials_provided:
                                    await asyncio.sleep(0.1)  # Poll for credentials (async)

                                    # Check if user cancelled (closed popup)
                                    with cancellation_lock:
                                        cancelled = session_cancellations.get(credentials_key, False)
                                    if cancelled:
                                        # Clear cancellation flag
                                        with cancellation_lock:
                                            del session_cancellations[credentials_key]
                                        # Send empty credentials to unblock subprocess, it will skip testing
                                        process.stdin.write("{}\n")
                                        process.stdin.flush()
                                        yield f"data: {json.dumps({'type': 'log', 'level': 'INFO', 'message': '⏭️  Configuration review skipped by user'})}\n\n"
                                        credentials_provided = True
                                        continue

                                    # Check if credentials were submitted for this session
                                    with credentials_lock:
                                        session_creds = session_credentials.get(credentials_key, {})
                                    if session_creds:
                                        # Send credentials to generate process stdin (wrapped format)
                                        creds_json = json.dumps({"credentials": session_creds})
                                        process.stdin.write(creds_json + '\n')
                                        process.stdin.flush()
                                        credentials_provided = True

                                # Don't collect for chat history
                                continue
                            except Exception as e:
                                print(f"Warning: Could not parse CONFIG_REVIEW_REQUIRED: {e}")
                                pass

                        # Check for TEST_LOG prefixed messages and route to test_log type
                        if line.startswith("TEST_LOG:"):
                            # Parse TEST_LOG:LEVEL:message format
                            try:
                                parts = line.split(":", 2)  # Split into at most 3 parts
                                if len(parts) >= 3:
                                    test_level = parts[1].strip()
                                    test_message = parts[2].strip()
                                    # Route to test_log type for Logs tab (don't add to chat)
                                    yield f"data: {json.dumps({'type': 'test_log', 'level': test_level, 'message': test_message})}\n\n"
                                    # Don't collect for chat history - logs tab only
                                    continue
                            except Exception:
                                # Fallback to regular processing if parsing fails
                                pass

                        # Check for SESSION_ID prefixed messages and capture for in-memory storage
                        if line.startswith("SESSION_ID:"):
                            try:
                                session_id = line.split(":", 1)[1].strip()
                                captured_session_id = session_id
                                # Don't yield to client - internal state management only
                                continue
                            except Exception as e:
                                print(f"Warning: Could not parse session ID: {e}")
                                # Don't block on parsing error, just continue
                                pass

                        # Determine log level based on content for regular messages
                        if line.startswith("ERROR:") or "❌" in line:
                            level = "ERROR"
                            message = line.replace("ERROR: ", "")
                        elif "⚠️" in line or "WARNING" in line:
                            level = "WARNING"
                            message = line
                        elif "✅" in line or "SUCCESS" in line:
                            level = "SUCCESS"
                            message = line
                        else:
                            level = "INFO"
                            message = line

                        # Collect logs for error analysis (not saved to chat history)
                        collected_logs.append(f"[{level}] {message}")

                        yield f"data: {json.dumps({'type': 'log', 'level': level, 'message': message})}\n\n"

                    except queue.Empty:
                        # No output available, check if process is complete
                        if return_code is not None:
                            # Process completed
                            break

                        # Add small delay to prevent busy waiting
                        await asyncio.sleep(0.1)
                        continue

                # Wait for threads to complete
                stdout_thread.join(timeout=5)
                stderr_thread.join(timeout=5)

                # Check if process is still running
                return_code = process.poll()  # Non-blocking check
                if return_code is None:
                    # Process is still running, don't wait for it
                    pass
                else:
                    # Process completed, clean up
                    if process_key in active_processes:
                        print(f"Process {process.pid} completed for {process_key} with return code {return_code}")
                        del active_processes[process_key]

                # Process any remaining output
                while not output_queue.empty():
                    try:
                        line = output_queue.get_nowait()
                        
                        # Check for TEST_LOG prefixed messages first
                        if line.startswith("TEST_LOG:"):
                            # Parse TEST_LOG:LEVEL:message format
                            try:
                                parts = line.split(":", 2)  # Split into at most 3 parts
                                if len(parts) >= 3:
                                    test_level = parts[1].strip()
                                    test_message = parts[2].strip()
                                    # Route to test_log type for Logs tab
                                    yield f"data: {json.dumps({'type': 'test_log', 'level': test_level, 'message': test_message})}\n\n"
                                    continue
                            except Exception:
                                # Fallback to regular processing if parsing fails
                                pass
                        
                        if line.startswith("ERROR:") or "❌" in line:
                            level = "ERROR"
                            message = line.replace("ERROR: ", "")
                        elif "⚠️" in line or "WARNING" in line:
                            level = "WARNING"
                            message = line
                        elif "✅" in line or "SUCCESS" in line:
                            level = "SUCCESS"
                            message = line
                        else:
                            level = "INFO"
                            message = line

                        yield f"data: {json.dumps({'type': 'log', 'level': level, 'message': message})}\n\n"
                    except queue.Empty:
                        break

                # Check final result
                connector_file = project_dir / "connector.py"
                if return_code == 0 and connector_file.exists():
                    yield f"data: {json.dumps({'type': 'log', 'level': 'SUCCESS', 'message': '✅ Connector generation completed successfully!'})}\n\n"

                    # Save simple completion message to chat history (not raw logs - file viewer shows content)
                    ai_message = {
                        "type": "ai",
                        "text": "✅ **Connector generation completed successfully!**\n\nYour connector has been generated. Use the file viewer to see the code.",
                        "timestamp": datetime.now().isoformat(),
                        "responseTime": 0,
                        "status": "completed"
                    }
                    save_connector_chat_message(current_user.username, project_name, ai_message, update_last_ai_message=initial_ai_message_saved)

                    # Persist session ID to project state directory for later resumption
                    if captured_session_id:
                        save_session_id(project_state_dir, captured_session_id)

                    # Mark generation as complete (stored in projects/ for state separation)
                    generation_complete_marker = project_state_dir / ".generation_complete"
                    generation_complete_marker.write_text(datetime.now().isoformat())
                    logger.info(f"Created generation complete marker at {generation_complete_marker}")

                    yield f"data: {json.dumps({'type': 'completion', 'status': 'success', 'project_name': project_name, 'project_path': str(project_dir)})}\n\n"
                else:
                    error_msg = f"❌ Generation failed with exit code {return_code}"
                    if not connector_file.exists():
                        error_msg += " - No connector.py file was created"

                    yield f"data: {json.dumps({'type': 'log', 'level': 'ERROR', 'message': error_msg})}\n\n"

                    # Classify error type
                    log_content = "\n".join(collected_logs)

                    # For generation, check if this connector has ever run successfully
                    # We use .run_success marker (not warehouse.db which could exist from uploads)
                    run_success_marker = project_dir / ".run_success"
                    is_first_run = not run_success_marker.exists()

                    error_classification = classify_error_type(log_content, is_first_run=is_first_run)

                    if error_classification['type'] == 'INFRA':
                        # INFRA issue - SDK/infrastructure problem, don't auto-fix
                        yield f"data: {json.dumps({'type': 'log', 'level': 'WARNING', 'message': '🔧 Infrastructure Issue: This is not a connector code problem'})}\n\n"

                        # Save to chat history
                        if collected_logs:
                            ai_message = {
                                "type": "ai",
                                "text": "\n".join(collected_logs) + f"\n\n{error_msg}\n\n🔧 **Infrastructure Issue Detected**\n\n{error_classification['guidance']}",
                                "timestamp": datetime.now().isoformat(),
                                "responseTime": 0,
                                "status": "error"
                            }
                            save_connector_chat_message(current_user.username, project_name, ai_message, update_last_ai_message=initial_ai_message_saved)

                        yield f"data: {json.dumps({'type': 'completion', 'status': 'infra_error', 'message': error_msg, 'guidance': error_classification['guidance']})}\n\n"

                    else:
                        # CODE issue - attempt automatic fix (like csdk-cmdd)
                        yield f"data: {json.dumps({'type': 'log', 'level': 'INFO', 'message': '🔧 Generation encountered issues, attempting to automatically fix...'})}\n\n"
                        
                        try:
                            # Call fixer agent with generation error logs (same as csdk-cmdd)
                            fix_script_path = Path(__file__).parent / "_fix_revise.py"
                            user_workspace_path = Path(f"workspaces/{current_user.username}")
                            
                            # Use the same API key as generation
                            env = os.environ.copy()
                            env['CSDKAI_ANTHROPIC_API_KEY'] = api_key
                            env['PYTHONUNBUFFERED'] = '1'

                            # Pass complete log content to fixer (like csdk-cmdd does with log_box.value)
                            fix_process = subprocess.Popen([
                                sys.executable, str(fix_script_path),
                                project_name,
                                str(user_workspace_path),
                                json.dumps(log_content),  # Pass all collected logs
                            ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               env=env, text=True, bufsize=1, universal_newlines=True)

                            # Stream fix output
                            fix_output = []
                            while True:
                                output = fix_process.stdout.readline()
                                if output == '' and fix_process.poll() is not None:
                                    break
                                if output:
                                    stripped_output = output.strip()

                                    # Check for CONFIG_REVIEW_REQUIRED message
                                    if stripped_output.startswith("CONFIG_REVIEW_REQUIRED:"):
                                        try:
                                            config_data = stripped_output.split(":", 1)[1].strip()
                                            config_json = json.loads(config_data)

                                            # Merge cached credentials into config (pre-fill popup with actual values)
                                            credentials_key = f"{current_user.session_token}:{project_name}"
                                            merged_config = config_json['configuration'].copy()

                                            # Try memory cache for credentials
                                            cached_creds = get_credentials_for_project(
                                                current_user.session_token, project_name
                                            )

                                            if cached_creds:
                                                # Replace "****" with actual cached values for pre-filling
                                                for key, value in merged_config.items():
                                                    if value == "****":
                                                        if key in cached_creds:
                                                            merged_config[key] = cached_creds[key]
                                                        else:
                                                            # No cached credential - show empty field
                                                            merged_config[key] = ""
                                                # Clear memory cache AFTER merging (forces polling to wait for new submission)
                                                with credentials_lock:
                                                    if credentials_key in session_credentials:
                                                        del session_credentials[credentials_key]
                                            else:
                                                # No cached credentials at all - replace "****" with empty strings
                                                for key, value in merged_config.items():
                                                    if value == "****":
                                                        merged_config[key] = ""

                                            # Read sensitivity metadata if it exists
                                            metadata_file = project_dir / ".config_metadata.json"
                                            sensitive_fields = []
                                            if metadata_file.exists():
                                                try:
                                                    with open(metadata_file) as f:
                                                        metadata = json.load(f)
                                                        sensitive_fields = metadata.get("sensitive_fields", [])
                                                except Exception as e:
                                                    print(f"Warning: Could not read metadata file: {e}")

                                            # Clear any stale cancellation flags before showing popup
                                            credentials_key = f"{current_user.session_token}:{project_name}"
                                            with cancellation_lock:
                                                if credentials_key in session_cancellations:
                                                    del session_cancellations[credentials_key]

                                            # Yield config review event with merged values AND sensitive fields
                                            config_review_response = {
                                                "type": "config_review",
                                                "configuration": merged_config,
                                                "sensitive_fields": sensitive_fields,
                                                "timestamp": datetime.now().isoformat()
                                            }
                                            yield f"data: {json.dumps(config_review_response)}\n\n"

                                            # Wait for credentials from session
                                            credentials_provided = False
                                            credentials_key = f"{current_user.session_token}:{project_name}"
                                            while not credentials_provided:
                                                await asyncio.sleep(0.1)  # Poll for credentials (async)

                                                # Check if user cancelled (closed popup)
                                                with cancellation_lock:
                                                    cancelled = session_cancellations.get(credentials_key, False)
                                                if cancelled:
                                                    # Clear cancellation flag
                                                    with cancellation_lock:
                                                        del session_cancellations[credentials_key]
                                                    # Send empty credentials to unblock subprocess, it will skip testing
                                                    fix_process.stdin.write("{}\n")
                                                    fix_process.stdin.flush()
                                                    yield f"data: {json.dumps({'type': 'log', 'level': 'INFO', 'message': '⏭️  Configuration review skipped by user'})}\n\n"
                                                    credentials_provided = True
                                                    continue

                                                # Check if credentials were submitted for this session
                                                with credentials_lock:
                                                    session_creds = session_credentials.get(credentials_key, {})
                                                if session_creds:
                                                    # Send credentials to fix process stdin (wrapped format)
                                                    creds_json = json.dumps({"credentials": session_creds})
                                                    fix_process.stdin.write(creds_json + '\n')
                                                    fix_process.stdin.flush()
                                                    credentials_provided = True
                                            continue
                                        except Exception as e:
                                            print(f"Warning: Could not parse CONFIG_REVIEW_REQUIRED: {e}")
                                            pass

                                    fix_output.append(stripped_output)
                                    yield f"data: {json.dumps({'type': 'log', 'level': 'INFO', 'message': stripped_output})}\n\n"
                            
                            fix_exit_code = fix_process.returncode
                            
                            if fix_exit_code == 0:
                                yield f"data: {json.dumps({'type': 'log', 'level': 'SUCCESS', 'message': '✅ Generation issues resolved! Connector is ready.'})}\n\n"
                                
                                # Save simple completion message to chat history (not raw logs)
                                ai_message = {
                                    "type": "ai",
                                    "text": "🔧 **Auto-Fix Applied**\n\n✅ **Connector generation completed!**\n\nIssues were automatically resolved. Use the file viewer to see the code.",
                                    "timestamp": datetime.now().isoformat(),
                                    "responseTime": 0,
                                    "status": "completed"
                                }
                                save_connector_chat_message(current_user.username, project_name, ai_message, update_last_ai_message=initial_ai_message_saved)

                                # Mark generation as complete (stored in projects/ for state separation)
                                generation_complete_marker = project_state_dir / ".generation_complete"
                                generation_complete_marker.write_text(datetime.now().isoformat())
                                logger.info(f"Created generation complete marker at {generation_complete_marker}")

                                yield f"data: {json.dumps({'type': 'completion', 'status': 'success_after_fix', 'project_name': project_name, 'project_path': str(project_dir)})}\n\n"
                            else:
                                yield f"data: {json.dumps({'type': 'log', 'level': 'ERROR', 'message': '❌ Could not resolve generation issues'})}\n\n"
                                
                                # Save failed fix attempt to chat history  
                                if collected_logs:
                                    ai_message = {
                                        "type": "ai",
                                        "text": "\n".join(collected_logs) + f"\n\n{error_msg}\n\n🔧 **Auto-Fix Attempted**\n\n" + "\n".join(fix_output) + "\n\n❌ **Fix Failed** - Manual intervention required.",
                                        "timestamp": datetime.now().isoformat(),
                                        "responseTime": 0,
                                        "status": "error"
                                    }
                                    save_connector_chat_message(current_user.username, project_name, ai_message, update_last_ai_message=initial_ai_message_saved)
                                
                                yield f"data: {json.dumps({'type': 'completion', 'status': 'error_fix_failed', 'message': error_msg})}\n\n"
                            
                        except Exception as fix_error:
                            fix_error_detail = log_and_format_error(fix_error, "Error during auto-fix")
                            yield f"data: {json.dumps({'type': 'log', 'level': 'ERROR', 'message': f'❌ {fix_error_detail}'})}\n\n"

                            # Save error to chat history
                            if collected_logs:
                                ai_message = {
                                    "type": "ai",
                                    "text": "\n".join(collected_logs) + f"\n\n{error_msg}\n\n❌ **Auto-Fix Error**: {fix_error_detail}",
                                    "timestamp": datetime.now().isoformat(),
                                    "responseTime": 0,
                                    "status": "error"
                                }
                                save_connector_chat_message(current_user.username, project_name, ai_message, update_last_ai_message=initial_ai_message_saved)
                            
                            yield f"data: {json.dumps({'type': 'completion', 'status': 'error', 'message': error_msg})}\n\n"
                    
                    # Clean up incomplete project only if no fix was attempted or fix failed
                    if project_dir.exists() and not connector_file.exists():
                        import shutil
                        shutil.rmtree(project_dir)

            except Exception as e:
                # Clean up process reference on error
                process_key = f"{current_user.username}:{project_name}"
                if process_key in active_processes:
                    del active_processes[process_key]

                error_detail = log_and_format_error(e, "Error during generation")
                error_msg = f"❌ {error_detail}"
                yield f"data: {json.dumps({'type': 'log', 'level': 'ERROR', 'message': error_msg})}\n\n"

                # Save generation logs to chat history even on exception
                if 'collected_logs' in locals() and collected_logs:
                    ai_message = {
                        "type": "ai",
                        "text": "\n".join(collected_logs) + f"\n\n{error_msg}",
                        "timestamp": datetime.now().isoformat(),
                        "responseTime": 0,  # Generation time
                        "status": "error"
                    }
                    save_connector_chat_message(current_user.username, project_name, ai_message, update_last_ai_message='initial_ai_message_saved' in locals() and initial_ai_message_saved)

                yield f"data: {json.dumps({'type': 'completion', 'status': 'error', 'message': error_msg})}\n\n"

        return StreamingResponse(
            generate_stream(),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        error_msg = log_and_format_error(e, "Error during connector generation")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg
        )

@app.post('/submit-config')
async def submit_config(request: SubmitConfigRequest, current_user: UserSession = Depends(get_current_user)):
    """
    Submit reviewed configuration with sensitive field markings.
    Stores sensitive values in session, saves masked config to disk, and sends to waiting process.
    """
    try:
        project_name = sanitize_path(request.project_name)
        user_workspace = get_user_workspace(current_user.username)
        connectors_dir = Path(user_workspace["connectors"])
        project_dir = connectors_dir / project_name

        # Validate project directory exists
        if not project_dir.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_name}' not found"
            )

        config_file = project_dir / "configuration.json"
        if not config_file.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="configuration.json not found in project"
            )

        # Store all configuration values
        all_values = dict(request.configuration)

        # Store in session cache for immediate use
        credentials_key = f"{current_user.session_token}:{project_name}"
        with credentials_lock:
            session_credentials[credentials_key] = all_values

        # Encrypt the ENTIRE configuration and write to file
        # The file will contain encrypted data (not valid JSON) = signal that credentials have been entered
        from encryption import encrypt_config
        encrypted_content = encrypt_config(current_user.username, all_values)
        config_file.write_text(encrypted_content)

        # Save sensitive fields metadata (so we can mask them when displaying)
        metadata_file = project_dir / ".config_metadata.json"
        metadata = {"sensitive_fields": list(request.sensitive_fields)}
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)

        logger.info(f"Saved encrypted configuration for project '{project_name}' by user {current_user.username} (sensitive fields: {len(request.sensitive_fields)})")

        # Find the waiting process and send credentials via stdin (for interactive flows)
        process_key = f"{current_user.username}:{project_name}"
        if process_key in active_processes:
            process = active_processes[process_key]
            if process and process.poll() is None and process.stdin:
                try:
                    # Send all configuration values as JSON to stdin
                    credentials_json = json.dumps({"credentials": all_values})
                    process.stdin.write(credentials_json + "\n")
                    process.stdin.flush()
                    logger.info(f"Sent credentials to waiting process for '{project_name}'")
                except Exception as e:
                    logger.error(f"Error sending credentials to process: {e}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Failed to send credentials to generation process"
                    )
            else:
                logger.warning(f"Process for '{project_name}' is not waiting for input")
        else:
            logger.warning(f"No active process found for '{project_name}', credentials stored for later use")

        return {
            "success": True,
            "message": "Configuration submitted successfully",
            "masked_fields": len(request.sensitive_fields)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting configuration: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit configuration. Please try again."
        )

@app.post('/cancel-config')
async def cancel_config(request: dict, current_user: UserSession = Depends(get_current_user)):
    """
    Cancel configuration review - user closed the popup without submitting.
    This signals the backend to skip testing and proceed.
    """
    try:
        project_name = request.get('project_name')
        if not project_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="project_name is required"
            )

        credentials_key = f"{current_user.session_token}:{project_name}"

        # Set cancellation flag
        with cancellation_lock:
            session_cancellations[credentials_key] = True

        logger.info(f"Configuration review cancelled for project '{project_name}' by user {current_user.username}")

        return {
            "success": True,
            "message": "Configuration review cancelled"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling configuration: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel configuration. Please try again."
        )

@app.get('/get-config/{project_name}')
async def get_config(project_name: str, current_user: UserSession = Depends(get_current_user)):
    """
    Retrieve configuration with merged credentials from session.
    Returns masked config file merged with actual values from session storage.
    """
    try:
        project_name = sanitize_path(project_name)
        user_workspace = get_user_workspace(current_user.username)
        connectors_dir = Path(user_workspace["connectors"])
        project_dir = connectors_dir / project_name

        # Check if project exists
        if not project_dir.exists():
            return {"exists": False, "configuration": {}}

        config_file = project_dir / "configuration.json"
        if not config_file.exists():
            return {"exists": False, "configuration": {}, "encrypted": False}

        # Read raw file content
        file_content = config_file.read_text()

        # Try to parse as JSON - if it fails, the file is encrypted
        is_encrypted = False
        try:
            config = json.loads(file_content)
        except json.JSONDecodeError:
            # Not valid JSON - check if it's encrypted
            if file_content.startswith('ENCRYPTED:'):
                # Decrypt encrypted content
                from encryption import decrypt_config
                try:
                    config = decrypt_config(current_user.username, file_content)
                    is_encrypted = True
                except Exception as decrypt_error:
                    # Can't decrypt - probably encrypted by different user/system
                    # Return empty config so user can enter new values
                    logger.warning(f"Cannot decrypt configuration for project '{project_name}' (may be from different user/system): {type(decrypt_error).__name__}")
                    return {
                        "exists": True,
                        "configuration": {},
                        "encrypted": True,
                        "decrypt_failed": True,
                        "message": "Configuration was encrypted by a different user or system. Please enter new values."
                    }
            else:
                # Not encrypted, just invalid JSON
                logger.error(f"Configuration file for project '{project_name}' is not valid JSON and not encrypted")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Configuration file is not valid JSON. Please check the file format."
                )

        # Read sensitive fields metadata if available
        sensitive_fields = []
        metadata_file = project_dir / ".config_metadata.json"
        if metadata_file.exists():
            try:
                with open(metadata_file) as f:
                    metadata = json.load(f)
                    sensitive_fields = metadata.get("sensitive_fields", [])
            except Exception:
                pass

        logger.info(f"Retrieved configuration for project '{project_name}' (encrypted={is_encrypted})")

        return {
            "exists": True,
            "configuration": config,
            "encrypted": is_encrypted,
            "sensitive_fields": sensitive_fields
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"Error retrieving configuration: {type(e).__name__}: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve configuration. Please try again."
        )

@app.post('/kill-generation')
async def kill_generation(request: dict, current_user: UserSession = Depends(get_current_user)):
    """Kill an active generation process"""
    try:
        project_name = request.get('project_name')
        if not project_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="project_name is required"
            )

        # Create a unique key for this user's project
        process_key = f"{current_user.username}:{project_name}"

        # Debug logging
        logger.info(f"Kill request for project: {project_name}, user: {current_user.username}")
        logger.info(f"Process key: {process_key}")
        logger.info(f"Active processes: {list(active_processes.keys())}")

        if process_key in active_processes:
            process = active_processes[process_key]

            # Kill the process immediately (user explicitly requested stop)
            try:
                print(f"Force killing process {process.pid} for {process_key} (user request)")
                success = terminate_process_immediately(process)
                
                # Remove from active processes
                del active_processes[process_key]
                
                if success:
                    logger.info(f"Successfully stopped generation process for project '{project_name}' by user {current_user.username}")
                    return {"success": True, "message": f"Generation process for '{project_name}' has been stopped"}
                else:
                    logger.warning(f"Process termination may not have completed cleanly for project '{project_name}'")
                    return {"success": True, "message": f"Generation process for '{project_name}' stop initiated (may still be terminating)"}

            except Exception as e:
                logger.error(f"Error killing process for project '{project_name}': {str(e)}")
                return {"success": False, "message": "Error stopping generation process. It may still be running."}
        else:
            return {"success": False, "message": f"No active generation process found for project '{project_name}'"}

    except Exception as e:
        error_msg = log_and_format_error(e, "Error stopping generation")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg
        )


@app.post('/kill-debug')
async def kill_debug(request: dict, current_user: UserSession = Depends(get_current_user)):
    """Kill an active debug process"""
    try:
        project_name = request.get('project_name')
        if not project_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="project_name is required"
            )

        # Create a unique key for this user's debug process
        process_key = f"{current_user.username}_{project_name}_debug"

        # Debug logging
        logger.info(f"Kill debug request for project: {project_name}, user: {current_user.username}")
        logger.info(f"Debug process key: {process_key}")
        logger.info(f"Active processes: {list(active_processes.keys())}")

        if process_key in active_processes:
            process = active_processes[process_key]

            # Kill the debug process immediately (user explicitly requested stop)
            try:
                print(f"Force killing debug process {process.pid} for {process_key} (user request)")
                success = terminate_process_immediately(process)
                
                # Remove from active processes
                del active_processes[process_key]
                
                if success:
                    logger.info(f"Successfully stopped debug process for project '{project_name}' by user {current_user.username}")
                    return {"success": True, "message": f"Debug process for '{project_name}' has been stopped"}
                else:
                    logger.warning(f"Debug process termination may not have completed cleanly for project '{project_name}'")
                    return {"success": True, "message": f"Debug process for '{project_name}' stop initiated (may still be terminating)"}

            except Exception as e:
                logger.error(f"Error killing debug process for project '{project_name}': {str(e)}")
                return {"success": False, "message": "Error stopping debug process. It may still be running."}
        else:
            return {"success": False, "message": f"No active debug process found for project '{project_name}'"}

    except Exception as e:
        error_msg = log_and_format_error(e, "Error stopping debug process")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg
        )


@app.post('/debug-connector-stream')
@limiter.limit("10/minute")
async def debug_connector_stream(request: Request, body: DebugConnectorRequest, current_user: UserSession = Depends(get_current_user)):
    """
    Debug a connector by running _run.py script with streaming output (rate limited: 10/min)
    """
    project_name = body.project_name
    trigger_context = body.trigger_context or "manual"  # Default to manual if not specified
    username = current_user.username

    # Check if project exists
    project_path = f"workspaces/{username}/connectors/{project_name}"
    if not os.path.exists(project_path):
        raise HTTPException(status_code=404, detail="Project not found")

    # Check if connector.py exists
    connector_file = os.path.join(project_path, "connector.py")
    if not os.path.exists(connector_file):
        raise HTTPException(status_code=404, detail="connector.py not found")

    async def generate_debug_stream():
        try:
            import queue
            import threading

            # Save user debug request to chat history
            user_message = {
                "type": "user",
                "text": f"Debug connector: {project_name}",
                "timestamp": datetime.now().isoformat()
            }
            save_connector_chat_message(username, project_name, user_message)

            # _run.py handles configuration decryption directly
            # Start the debug process
            # Use absolute path to _run.py in the backend app directory
            run_script_path = os.path.join(os.path.dirname(__file__), "_run.py")
            debug_command = ["python", run_script_path, project_name, f"../workspaces/{username}", "run"]
            logger.info(f"Debug command: {debug_command}")
            logger.info(f"Working directory: {project_path}")
            logger.info(f"Run script path: {run_script_path}")

            # stdin=DEVNULL prevents prompt_toolkit EOFError when fivetran CLI
            # tries to read interactive input (there's no TTY in web server context)
            process = subprocess.Popen(
                debug_command,
                cwd=os.path.dirname(__file__),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
                env={**os.environ, "CSDKAI_ANTHROPIC_API_KEY": os.getenv("CSDKAI_ANTHROPIC_API_KEY", "")},
                preexec_fn=os.setsid if os.name != 'nt' else None
            )

            # Store process for potential cancellation
            process_key = f"{username}_{project_name}_debug"
            active_processes[process_key] = process
            
            # Log process lifecycle
            print(f"Started debug process {process.pid} for {process_key}")

            # Use threading for non-blocking output capture
            output_queue = queue.Queue()

            def stream_output(pipe, queue):
                for line in iter(pipe.readline, ''):
                    queue.put(line)
                pipe.close()

            stdout_thread = threading.Thread(target=stream_output, args=(process.stdout, output_queue))
            stderr_thread = threading.Thread(target=stream_output, args=(process.stderr, output_queue))

            stdout_thread.start()
            stderr_thread.start()

            collected_logs = []

            while True:
                # Check if process is still running
                return_code = process.poll()
                if return_code is not None:
                    break

                # Try to get output from queue (non-blocking)
                try:
                    while True:
                        line = output_queue.get_nowait()
                        line_stripped = strip_ansi_codes(line.rstrip())

                        if line_stripped:
                            # Parse log level from line content
                            if line_stripped.startswith("ERROR:") or "❌" in line_stripped:
                                level = "ERROR"
                                message = line_stripped.replace("ERROR: ", "")
                            elif "⚠️" in line_stripped or "WARNING" in line_stripped:
                                level = "WARNING"
                                message = line_stripped
                            elif "✅" in line_stripped or "SUCCESS" in line_stripped:
                                level = "SUCCESS"
                                message = line_stripped
                            elif "ℹ️" in line_stripped or "INFO" in line_stripped:
                                level = "INFO"
                                message = line_stripped
                            else:
                                level = "INFO"
                                message = line_stripped

                            # Send log to frontend
                            log_response = {
                                "type": "log",
                                "level": level,
                                "message": message,
                                "timestamp": datetime.now().isoformat()
                            }
                            yield f"data: {json.dumps(log_response)}\n\n"

                            # Collect logs for chat history
                            collected_logs.append(f"[{level}] {message}")

                except queue.Empty:
                    pass

                # Small delay to prevent busy waiting
                await asyncio.sleep(0.1)

            # Wait for threads to finish
            stdout_thread.join(timeout=5)
            stderr_thread.join(timeout=5)

            # Wait for process to complete
            return_code = process.wait()

            # Log the return code and any remaining output
            logger.info(f"Debug process completed with return code: {return_code}")

            # Get any remaining output from the queue
            remaining_output = []
            try:
                while True:
                    line = output_queue.get_nowait()
                    line_stripped = strip_ansi_codes(line.rstrip())
                    remaining_output.append(line_stripped)
                    
                    # Also collect remaining output for auto-fix (like main loop does)
                    if line_stripped:
                        # Parse log level from remaining output
                        if line_stripped.startswith("ERROR:") or "❌" in line_stripped:
                            level = "ERROR"
                            message = line_stripped.replace("ERROR: ", "")
                        elif "⚠️" in line_stripped or "WARNING" in line_stripped:
                            level = "WARNING"
                            message = line_stripped
                        elif "✅" in line_stripped or "SUCCESS" in line_stripped:
                            level = "SUCCESS"
                            message = line_stripped
                        else:
                            level = "INFO"
                            message = line_stripped
                        
                        # Collect for auto-fix (matching main loop pattern)
                        collected_logs.append(f"[{level}] {message}")
            except queue.Empty:
                pass

            if remaining_output:
                logger.info(f"Remaining output: {remaining_output}")

            # Handle completion status
            if return_code == 0:
                # Success case - create .run_success marker to track first successful run
                run_success_marker = Path(project_path) / ".run_success"
                try:
                    run_success_marker.touch()
                except Exception as e:
                    logger.warning(f"Could not create .run_success marker: {e}")

                completion_status = "Debug run completed successfully"
                ai_message = {
                    "type": "ai",
                    "text": completion_status,
                    "timestamp": datetime.now().isoformat(),
                    "responseTime": 0
                }
                save_connector_chat_message(username, project_name, ai_message)

                final_response = {
                    "type": "complete",
                    "success": True,
                    "timestamp": datetime.now().isoformat()
                }
                yield f"data: {json.dumps(final_response)}\n\n"
            else:
                # Debug failed - classify error type
                log_content = "\n".join(collected_logs)

                # Check if this is a first run (no .run_success marker = never succeeded)
                # We use .run_success marker (not warehouse.db which could exist from uploads)
                run_success_marker = Path(project_path) / ".run_success"
                is_first_run = not run_success_marker.exists()

                error_classification = classify_error_type(log_content, is_first_run=is_first_run)

                if error_classification['type'] == 'FIRST_RUN':
                    # First run failure - likely config/credentials issue
                    error_msg = f"Debug failed (return code: {return_code}) - Likely Configuration Issue"
                    guidance_response = {
                        "type": "log",
                        "level": "WARNING",
                        "message": "💡 First Run: Please verify your configuration values (API keys, usernames, endpoints)",
                        "timestamp": datetime.now().isoformat()
                    }
                    yield f"data: {json.dumps(guidance_response)}\n\n"

                    ai_message = {
                        "type": "ai",
                        "text": f"Debug failed (return code: {return_code})\n\n💡 **First Run Issue**\n\nThis connector has not run successfully yet. {error_classification['guidance']}",
                        "timestamp": datetime.now().isoformat(),
                        "responseTime": 0
                    }
                    save_connector_chat_message(username, project_name, ai_message)

                    final_response = {
                        "type": "complete",
                        "success": False,
                        "message": error_msg,
                        "error_type": "first_run",
                        "timestamp": datetime.now().isoformat()
                    }
                    yield f"data: {json.dumps(final_response)}\n\n"

                elif error_classification['type'] == 'INFRA':
                    # INFRA issue - SDK/infrastructure problem, don't auto-fix
                    error_msg = f"Debug failed (return code: {return_code}) - Infrastructure Issue"
                    guidance_response = {
                        "type": "log",
                        "level": "WARNING",
                        "message": "🔧 Infrastructure Issue: This is not a connector code problem",
                        "timestamp": datetime.now().isoformat()
                    }
                    yield f"data: {json.dumps(guidance_response)}\n\n"

                    ai_message = {
                        "type": "ai",
                        "text": f"Debug failed (return code: {return_code})\n\n🔧 **Infrastructure Issue Detected**\n\n{error_classification['guidance']}",
                        "timestamp": datetime.now().isoformat(),
                        "responseTime": 0
                    }
                    save_connector_chat_message(username, project_name, ai_message)

                    final_response = {
                        "type": "complete",
                        "success": False,
                        "message": error_msg,
                        "error_type": "infra",
                        "timestamp": datetime.now().isoformat()
                    }
                    yield f"data: {json.dumps(final_response)}\n\n"

                else:
                    # CODE issue - check trigger context before attempting auto-fix
                    if trigger_context == "generation":
                        # Auto-fix only for generation/revise workflows
                        fix_response = {
                            "type": "log",
                            "level": "INFO",
                            "message": "🔧 Attempting to automatically fix the connector...",
                            "timestamp": datetime.now().isoformat()
                        }
                        yield f"data: {json.dumps(fix_response)}\n\n"

                        try:
                            # Call fixer agent with debug error logs (same as csdk-cmdd)
                            fix_script_path = Path(__file__).parent / "_fix_revise.py"
                            user_workspace_path = Path(f"workspaces/{username}")
                            
                            # Use environment API key
                            api_key = get_anthropic_api_key()
                            if not api_key:
                                yield json.dumps({"type": "error", "message": "CSDKAI_ANTHROPIC_API_KEY (or ANTHROPIC_API_KEY) environment variable not set"}) + '\n'
                                return

                            env = os.environ.copy()
                            env['CSDKAI_ANTHROPIC_API_KEY'] = api_key
                            env['PYTHONUNBUFFERED'] = '1'

                            # Pass complete log content to fixer (like csdk-cmdd does)
                            fix_process = subprocess.Popen([
                                sys.executable, str(fix_script_path),
                                project_name,
                                str(user_workspace_path),
                                json.dumps(log_content),  # Pass all collected debug logs
                            ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               env=env, text=True, bufsize=1, universal_newlines=True)

                            # Stream fix output
                            fix_output = []
                            while True:
                                output = fix_process.stdout.readline()
                                if output == '' and fix_process.poll() is not None:
                                    break
                                if output:
                                    stripped_output = output.strip()

                                    # Check for CONFIG_REVIEW_REQUIRED message
                                    if stripped_output.startswith("CONFIG_REVIEW_REQUIRED:"):
                                        try:
                                            config_data = stripped_output.split(":", 1)[1].strip()
                                            config_json = json.loads(config_data)

                                            # Merge cached credentials into config (pre-fill popup with actual values)
                                            credentials_key = f"{current_user.session_token}:{project_name}"
                                            merged_config = config_json['configuration'].copy()

                                            # Try memory cache for credentials
                                            cached_creds = get_credentials_for_project(
                                                current_user.session_token, project_name
                                            )

                                            if cached_creds:
                                                # Replace "****" with actual cached values for pre-filling
                                                for key, value in merged_config.items():
                                                    if value == "****":
                                                        if key in cached_creds:
                                                            merged_config[key] = cached_creds[key]
                                                        else:
                                                            # No cached credential - show empty field
                                                            merged_config[key] = ""
                                                # Clear memory cache AFTER merging (forces polling to wait for new submission)
                                                with credentials_lock:
                                                    if credentials_key in session_credentials:
                                                        del session_credentials[credentials_key]
                                            else:
                                                # No cached credentials at all - replace "****" with empty strings
                                                for key, value in merged_config.items():
                                                    if value == "****":
                                                        merged_config[key] = ""

                                            # Read sensitivity metadata if it exists
                                            metadata_file = project_dir / ".config_metadata.json"
                                            sensitive_fields = []
                                            if metadata_file.exists():
                                                try:
                                                    with open(metadata_file) as f:
                                                        metadata = json.load(f)
                                                        sensitive_fields = metadata.get("sensitive_fields", [])
                                                except Exception as e:
                                                    print(f"Warning: Could not read metadata file: {e}")

                                            # Clear any stale cancellation flags before showing popup
                                            credentials_key = f"{current_user.session_token}:{project_name}"
                                            with cancellation_lock:
                                                if credentials_key in session_cancellations:
                                                    del session_cancellations[credentials_key]

                                            # Yield config review event with merged values AND sensitive fields
                                            config_review_response = {
                                                "type": "config_review",
                                                "configuration": merged_config,
                                                "sensitive_fields": sensitive_fields,
                                                "timestamp": datetime.now().isoformat()
                                            }
                                            yield f"data: {json.dumps(config_review_response)}\n\n"

                                            # Wait for credentials from session
                                            credentials_provided = False
                                            credentials_key = f"{current_user.session_token}:{project_name}"
                                            while not credentials_provided:
                                                await asyncio.sleep(0.1)  # Poll for credentials (async)

                                                # Check if user cancelled (closed popup)
                                                with cancellation_lock:
                                                    cancelled = session_cancellations.get(credentials_key, False)
                                                if cancelled:
                                                    # Clear cancellation flag
                                                    with cancellation_lock:
                                                        del session_cancellations[credentials_key]
                                                    # Send empty credentials to unblock subprocess, it will skip testing
                                                    fix_process.stdin.write("{}\n")
                                                    fix_process.stdin.flush()
                                                    yield f"data: {json.dumps({'type': 'log', 'level': 'INFO', 'message': '⏭️  Configuration review skipped by user'})}\n\n"
                                                    credentials_provided = True
                                                    continue

                                                # Check if credentials were submitted for this session
                                                with credentials_lock:
                                                    session_creds = session_credentials.get(credentials_key, {})
                                                if session_creds:
                                                    # Send credentials to fix process stdin (wrapped format)
                                                    creds_json = json.dumps({"credentials": session_creds})
                                                    fix_process.stdin.write(creds_json + '\n')
                                                    fix_process.stdin.flush()
                                                    credentials_provided = True
                                            continue
                                        except Exception as e:
                                            print(f"Warning: Could not parse CONFIG_REVIEW_REQUIRED: {e}")
                                            pass

                                    fix_output.append(stripped_output)
                                    fix_log_response = {
                                        "type": "log",
                                        "level": "INFO",
                                        "message": stripped_output,
                                        "timestamp": datetime.now().isoformat()
                                    }
                                    yield f"data: {json.dumps(fix_log_response)}\n\n"
                            
                            fix_exit_code = fix_process.returncode
                            
                            if fix_exit_code == 0:
                                # Fix successful
                                success_response = {
                                    "type": "log",
                                    "level": "SUCCESS",
                                    "message": "✅ Connector fixed, state cleared, please try running the connector again",
                                    "timestamp": datetime.now().isoformat()
                                }
                                yield f"data: {json.dumps(success_response)}\n\n"
                                
                                ai_message = {
                                    "type": "ai",
                                    "text": f"Debug failed (return code: {return_code})\n\n🔧 **Auto-Fix Applied**\n\n" + "\n".join(fix_output) + "\n\n✅ **Fix Complete** - Connector is ready to test again.",
                                    "timestamp": datetime.now().isoformat(),
                                    "responseTime": 0
                                }
                                save_connector_chat_message(username, project_name, ai_message)
                                
                                final_response = {
                                    "type": "complete", 
                                    "success": True,
                                    "message": "Fixed and ready to retry",
                                    "fixed": True,
                                    "timestamp": datetime.now().isoformat()
                                }
                                yield f"data: {json.dumps(final_response)}\n\n"
                            else:
                                # Fix failed
                                failure_response = {
                                    "type": "log",
                                    "level": "ERROR",
                                    "message": "❌ Unable to fix the code",
                                    "timestamp": datetime.now().isoformat()
                                }
                                yield f"data: {json.dumps(failure_response)}\n\n"
                                
                                ai_message = {
                                    "type": "ai",
                                    "text": f"Debug failed (return code: {return_code})\n\n🔧 **Auto-Fix Attempted**\n\n" + "\n".join(fix_output) + "\n\n❌ **Fix Failed** - Manual intervention required.",
                                    "timestamp": datetime.now().isoformat(),
                                    "responseTime": 0
                                }
                                save_connector_chat_message(username, project_name, ai_message)
                                
                                final_response = {
                                    "type": "complete",
                                    "success": False,
                                    "message": f"Debug failed (return code: {return_code}) and auto-fix failed", 
                                    "timestamp": datetime.now().isoformat()
                                }
                                yield f"data: {json.dumps(final_response)}\n\n"
                                
                        except Exception as fix_error:
                            # Fix process error
                            fix_error_detail = log_and_format_error(fix_error, "Error during auto-fix")
                            error_response = {
                                "type": "log",
                                "level": "ERROR",
                                "message": f"❌ {fix_error_detail}",
                                "timestamp": datetime.now().isoformat()
                            }
                            yield f"data: {json.dumps(error_response)}\n\n"

                            ai_message = {
                                "type": "ai",
                                "text": f"Debug failed (return code: {return_code})\n\n❌ **Auto-Fix Error**: {fix_error_detail}",
                                "timestamp": datetime.now().isoformat(),
                                "responseTime": 0
                            }
                            save_connector_chat_message(username, project_name, ai_message)
                            
                            final_response = {
                                "type": "complete",
                                "success": False,
                                "message": f"Debug failed (return code: {return_code})",
                                "timestamp": datetime.now().isoformat()
                            }
                            yield f"data: {json.dumps(final_response)}\n\n"
                    else:
                        # Manual debug - show failure with option to trigger AI fix
                        ai_message = {
                            "type": "ai",
                            "text": f"Debug failed (return code: {return_code})\n\n❌ **Debug Failed**\n\nPlease check your connector implementation and configuration. Common issues:\n\n• Verify API credentials are correct\n• Check network connectivity\n• Review error messages above for specific issues\n• Ensure all required fields are properly configured",
                            "timestamp": datetime.now().isoformat()
                        }
                        save_connector_chat_message(username, project_name, ai_message)

                        # Send response with offer_ai_fix flag so frontend can show "Let AI fix" button
                        final_response = {
                            "type": "complete",
                            "success": False,
                            "message": f"Debug failed (return code: {return_code})",
                            "offer_ai_fix": True,
                            "log_content": log_content,  # Include logs so frontend can pass back for AI fix
                            "timestamp": datetime.now().isoformat()
                        }
                        yield f"data: {json.dumps(final_response)}\n\n"

        except Exception as e:
            error_detail = log_and_format_error(e, "Error during debugging")
            error_response = {
                "type": "error",
                "message": error_detail,
                "timestamp": datetime.now().isoformat()
            }
            yield f"data: {json.dumps(error_response)}\n\n"
        finally:
            # Clean up process reference and ensure termination
            process_key = f"{username}_{project_name}_debug"
            if process_key in active_processes:
                process = active_processes[process_key]
                if process.poll() is None:
                    print(f"Cleaning up debug process {process.pid} for {process_key}")
                    terminate_process_gracefully(process, timeout=5)
                else:
                    print(f"Debug process {process.pid} for {process_key} completed with return code {process.returncode}")
                del active_processes[process_key]

            # Clean up any leftover temp files (named pipes)
            user_workspace = get_user_workspace(username)
            connectors_dir = Path(user_workspace["connectors"])
            project_dir = connectors_dir / project_name
            for temp_file in [".config_pipe"]:
                temp_path = project_dir / temp_file
                if temp_path.exists():
                    try:
                        temp_path.unlink()
                        logger.info(f"Cleaned up {temp_file} for debug: {project_name}")
                    except Exception as e:
                        logger.warning(f"Could not cleanup {temp_file}: {e}")

    return StreamingResponse(
        generate_debug_stream(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


def filter_fixer_output_for_user(lines: list[str]) -> list[str]:
    """
    Filter fixer output to show only user-relevant content.
    Removes internal messages, prompts, and verbose SDK details.
    """
    filtered = []
    skip_patterns = [
        "CONFIG_REVIEW_REQUIRED:",
        "📋 Created backup:",
        "🔗 Attempting to resume",
        "ℹ️  No previous session",
        "⏸️  Please review configuration",
        "⏸️  Waiting for credentials",
        "✅ Configuration received",
        "🧪 Resetting state",
        "🧪 Testing fix",
        "Session expired or invalid",
        "=" * 20,  # Separator lines
        # Internal prompt/instruction patterns
        "REQUIRED OUTPUT FORMAT",
        "Your response MUST",
        "MUST include",
        "MANDATORY",
        "Format your response",
        "**Format your response",
        "Include in your response",
        "CRITICAL:",
        "IMPORTANT:",
        "**CRITICAL",
        "**IMPORTANT",
        "After completing",
        "provide a comprehensive",
        "Real-time Progress",
        # Internal markdown file patterns
        "# Fivetran Connector",
        "## FIVETRAN CONNECTOR",
        "### Common Error Categories",
        "### Debugging Commands",
        "## BEST PRACTICES",
        "### Code Validation Requirements",
        "### Runtime Environment",
        "## TASK: Analyze",
        "### Instructions for the fixer",
        "**TOOL USAGE GUIDELINES:**",
        "## **SYSTEMATIC DEBUGGING APPROACH:**",
        "### Real-time Progress",
        "## 📋 COMMON ERROR PATTERNS",
        "### **Type Annotation Errors**",
        "### **Authentication Errors**",
        "### **Configuration Errors**",
        "### **Import/Syntax Errors**",
        "### **Logging Method Errors**",
        "**REMEMBER**:",
        "**Common USER issues",
        "**For CODE errors**:",
        "**For USER errors**:",
        "Use Task tool with:",
        "The fixer subagent should be",
        "subagent_type:",
        "- description:",
        "- prompt:",
    ]

    # Also skip lines that look like internal SDK messages or markdown prompts
    for line in lines:
        stripped = line.strip()

        # Skip empty lines
        if not stripped:
            continue

        # Skip lines matching skip patterns
        if any(pattern in stripped for pattern in skip_patterns):
            continue

        # Skip lines that are just equals signs (separators)
        if stripped.replace("=", "") == "":
            continue

        # Skip lines that look like markdown headers for internal sections
        if stripped.startswith("##") and any(word in stripped.lower() for word in ["mandatory", "format", "output", "requirements", "best practices", "common error", "debugging"]):
            continue

        # Skip lines that look like internal markdown list items from the prompt
        if stripped.startswith("- **") and any(word in stripped.lower() for word in ["authentication", "network", "data format", "configuration", "code logic", "primary keys", "logging", "checkpoints", "error handling"]):
            continue

        # Keep the line
        filtered.append(line)

    return filtered


def filter_fixer_output_for_chat(lines: list[str]) -> list[str]:
    """
    Filter fixer output for chat message - more aggressive filtering.
    Shows only the key findings, tool calls, and changes made.
    """
    result_lines = []
    in_relevant_section = False
    skip_until_separator = False
    in_skip_block = False

    # Patterns that indicate internal/prompt content to skip entirely
    skip_section_markers = [
        "REQUIRED OUTPUT FORMAT",
        "MANDATORY",
        "Your response MUST",
        "Format your response",
        "Real-time Progress",
        "After completing the fix",
        "# Fivetran Connector",
        "## FIVETRAN CONNECTOR",
        "## BEST PRACTICES",
        "## TASK: Analyze",
        "### Instructions for the fixer",
        "**TOOL USAGE GUIDELINES:**",
        "## **SYSTEMATIC DEBUGGING APPROACH:**",
        "## 📋 COMMON ERROR PATTERNS",
        "**REMEMBER**:",
        "**Common USER issues",
        "**For CODE errors**:",
        "**For USER errors**:",
        "Use Task tool with:",
        "The fixer subagent should be",
    ]

    # Patterns that indicate user-relevant content
    relevant_markers = [
        "ERROR_TYPE:",
        "PROBLEM IDENTIFIED:",
        "SOLUTION APPLIED:",
        "FILES MODIFIED:",
        "🔧 CODE ISSUE DETECTED",
        "🔍 USER CONFIGURATION ISSUE",
        "❌ AI FIX INCOMPLETE",
        "I identified",
        "I found",
        "I fixed",
        "The issue was",
        "The problem was",
        "The error",
        "Changed",
        "Updated",
        "Modified",
        "Replaced",
        # Tool call indicators
        "Reading file",
        "Editing file",
        "Using Read tool",
        "Using Edit tool",
        "Using WebFetch",
        "Analyzing",
        "Examining",
        "Checking",
        "Looking at",
        "connector.py",
        "configuration.json",
    ]

    for line in lines:
        stripped = line.strip()

        # Skip empty lines
        if not stripped:
            continue

        # Check if we should skip this section
        if any(marker in stripped for marker in skip_section_markers):
            skip_until_separator = True
            in_skip_block = True
            continue

        # Reset skip flag at separator or markdown header changes
        if stripped.replace("=", "") == "" and len(stripped) > 10:
            skip_until_separator = False
            in_relevant_section = False
            in_skip_block = False
            continue

        # Also reset on major section changes (### headers not in skip list)
        if stripped.startswith("###") and not any(marker in stripped for marker in skip_section_markers):
            in_skip_block = False

        # If in skip mode, continue
        if skip_until_separator or in_skip_block:
            # But check if we hit a relevant marker - that should break us out
            if any(marker in stripped for marker in relevant_markers):
                skip_until_separator = False
                in_skip_block = False
                in_relevant_section = True
                result_lines.append(line)
            continue

        # Check if this line starts a relevant section
        if any(marker in stripped for marker in relevant_markers):
            in_relevant_section = True
            result_lines.append(line)
            continue

        # If we're in a relevant section, include content (up to a reasonable length)
        if in_relevant_section:
            # Stop including if we hit internal content
            if any(marker in stripped for marker in ["CRITICAL", "IMPORTANT", "MANDATORY", "```bash", "fivetran debug"]):
                in_relevant_section = False
                continue
            result_lines.append(line)

    # If no relevant sections found, return a simple summary
    if not result_lines:
        return ["AI analyzed the connector and attempted fixes."]

    return result_lines


@app.post('/trigger-ai-fix-stream')
@limiter.limit("10/minute")
async def trigger_ai_fix_stream(request: Request, body: TriggerAIFixRequest, current_user: UserSession = Depends(get_current_user)):
    """
    Trigger AI fixer for a connector when user clicks "Let AI fix" button.
    This runs the same auto-fix logic as generation context but initiated manually.
    (rate limited: 10/min)
    """
    project_name = body.project_name
    log_content = body.log_content
    username = current_user.username

    # Check if project exists
    project_path = f"workspaces/{username}/connectors/{project_name}"
    if not os.path.exists(project_path):
        raise HTTPException(status_code=404, detail="Project not found")

    async def generate_fix_stream():
        try:
            fix_response = {
                "type": "log",
                "level": "INFO",
                "message": "🔧 AI is analyzing the issue and attempting to fix the connector...",
                "timestamp": datetime.now().isoformat()
            }
            yield f"data: {json.dumps(fix_response)}\n\n"

            # Call fixer agent with debug error logs
            fix_script_path = Path(__file__).parent / "_fix_revise.py"
            user_workspace_path = Path(f"workspaces/{username}")

            # Use environment API key
            api_key = get_anthropic_api_key()
            if not api_key:
                yield f"data: {json.dumps({'type': 'error', 'message': 'CSDKAI_ANTHROPIC_API_KEY (or ANTHROPIC_API_KEY) environment variable not set'})}\n\n"
                return

            env = os.environ.copy()
            env['CSDKAI_ANTHROPIC_API_KEY'] = api_key
            env['PYTHONUNBUFFERED'] = '1'

            # Pass log content to fixer
            fix_process = subprocess.Popen([
                sys.executable, str(fix_script_path),
                project_name,
                str(user_workspace_path),
                log_content,  # Already JSON string from frontend
            ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
               env=env, text=True, bufsize=1, universal_newlines=True)

            # Stream fix output
            fix_output = []
            project_dir = Path(project_path)
            while True:
                output = fix_process.stdout.readline()
                if output == '' and fix_process.poll() is not None:
                    break
                if output:
                    stripped_output = output.strip()

                    # Check for CONFIG_REVIEW_REQUIRED message
                    if stripped_output.startswith("CONFIG_REVIEW_REQUIRED:"):
                        try:
                            config_data = stripped_output.split(":", 1)[1].strip()
                            config_json = json.loads(config_data)

                            # Merge cached credentials into config
                            credentials_key = f"{current_user.session_token}:{project_name}"
                            merged_config = config_json['configuration'].copy()

                            cached_creds = get_credentials_for_project(
                                current_user.session_token, project_name
                            )

                            if cached_creds:
                                for key, value in merged_config.items():
                                    if value == "****":
                                        if key in cached_creds:
                                            merged_config[key] = cached_creds[key]
                                        else:
                                            merged_config[key] = ""
                                with credentials_lock:
                                    if credentials_key in session_credentials:
                                        del session_credentials[credentials_key]
                            else:
                                for key, value in merged_config.items():
                                    if value == "****":
                                        merged_config[key] = ""

                            # Read sensitivity metadata
                            metadata_file = project_dir / ".config_metadata.json"
                            sensitive_fields = []
                            if metadata_file.exists():
                                try:
                                    with open(metadata_file) as f:
                                        metadata = json.load(f)
                                        sensitive_fields = metadata.get("sensitive_fields", [])
                                except Exception as e:
                                    print(f"Warning: Could not read metadata file: {e}")

                            # Clear stale cancellation flags
                            with cancellation_lock:
                                if credentials_key in session_cancellations:
                                    del session_cancellations[credentials_key]

                            # Yield config review event
                            config_review_response = {
                                "type": "config_review",
                                "configuration": merged_config,
                                "sensitive_fields": sensitive_fields,
                                "timestamp": datetime.now().isoformat()
                            }
                            yield f"data: {json.dumps(config_review_response)}\n\n"

                            # Wait for credentials from session
                            credentials_provided = False
                            while not credentials_provided:
                                await asyncio.sleep(0.1)

                                with cancellation_lock:
                                    cancelled = session_cancellations.get(credentials_key, False)
                                if cancelled:
                                    with cancellation_lock:
                                        del session_cancellations[credentials_key]
                                    fix_process.stdin.write("{}\n")
                                    fix_process.stdin.flush()
                                    yield f"data: {json.dumps({'type': 'log', 'level': 'INFO', 'message': '⏭️  Configuration review skipped by user'})}\n\n"
                                    credentials_provided = True
                                    continue

                                with credentials_lock:
                                    session_creds = session_credentials.get(credentials_key, {})
                                if session_creds:
                                    creds_json = json.dumps({"credentials": session_creds})
                                    fix_process.stdin.write(creds_json + '\n')
                                    fix_process.stdin.flush()
                                    credentials_provided = True
                            continue
                        except Exception as e:
                            print(f"Warning: Could not parse CONFIG_REVIEW_REQUIRED: {e}")
                            pass

                    fix_output.append(stripped_output)

                    # Filter for streaming to user (skip internal messages)
                    filtered_for_stream = filter_fixer_output_for_user([stripped_output])
                    if filtered_for_stream:
                        fix_log_response = {
                            "type": "log",
                            "level": "INFO",
                            "message": stripped_output,
                            "timestamp": datetime.now().isoformat()
                        }
                        yield f"data: {json.dumps(fix_log_response)}\n\n"

            fix_exit_code = fix_process.returncode

            # Filter output for chat message (more aggressive filtering)
            filtered_for_chat = filter_fixer_output_for_chat(fix_output)
            chat_output = "\n".join(filtered_for_chat) if filtered_for_chat else "AI analyzed and processed the connector."

            if fix_exit_code == 0:
                # Fix successful
                success_response = {
                    "type": "log",
                    "level": "SUCCESS",
                    "message": "✅ Connector fixed! Please run debug again to verify.",
                    "timestamp": datetime.now().isoformat()
                }
                yield f"data: {json.dumps(success_response)}\n\n"

                ai_message = {
                    "type": "ai",
                    "text": f"🔧 **AI Fix Applied**\n\n{chat_output}\n\n✅ **Fix Complete** - Connector is ready to test again.",
                    "timestamp": datetime.now().isoformat()
                }
                save_connector_chat_message(username, project_name, ai_message)

                final_response = {
                    "type": "complete",
                    "success": True,
                    "message": "Fixed and ready to retry",
                    "fixed": True,
                    "timestamp": datetime.now().isoformat()
                }
                yield f"data: {json.dumps(final_response)}\n\n"
            else:
                # Fix failed
                failure_response = {
                    "type": "log",
                    "level": "ERROR",
                    "message": "❌ AI was unable to fix the issue automatically",
                    "timestamp": datetime.now().isoformat()
                }
                yield f"data: {json.dumps(failure_response)}\n\n"

                ai_message = {
                    "type": "ai",
                    "text": f"🔧 **AI Fix Attempted**\n\n{chat_output}\n\n❌ **Fix Failed** - Manual intervention may be required.",
                    "timestamp": datetime.now().isoformat()
                }
                save_connector_chat_message(username, project_name, ai_message)

                final_response = {
                    "type": "complete",
                    "success": False,
                    "message": "AI fix failed",
                    "timestamp": datetime.now().isoformat()
                }
                yield f"data: {json.dumps(final_response)}\n\n"

        except Exception as e:
            error_detail = log_and_format_error(e, "Error during AI fix")
            error_response = {
                "type": "error",
                "message": error_detail,
                "timestamp": datetime.now().isoformat()
            }
            yield f"data: {json.dumps(error_response)}\n\n"

    return StreamingResponse(
        generate_fix_stream(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

@app.post('/validate-description-stream')
@limiter.limit("10/minute")
async def validate_description_stream(request: Request, body: ValidateDescriptionRequest, current_user: UserSession = Depends(get_current_user)):
    """
    Validate a connector description with interactive conversation streaming (rate limited: 10/min)
    """
    try:
        # Validate required fields
        if not body.project_name or not body.description:
            logger.warning(f"Missing required fields in validation request from user {current_user.username}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing required fields: project_name, description"
            )

        # Validate project name
        if not validate_project_name(body.project_name):
            logger.warning(f"Invalid project name '{body.project_name}' from user {current_user.username}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid project name. Must start with a letter or underscore, and can only contain lowercase letters, numbers, and underscores"
            )

        # Sanitize project name
        project_name = sanitize_path(body.project_name)

        # Get user workspace
        user_workspace = get_user_workspace(current_user.username)
        user_workspace_path = Path(user_workspace["base"])

        logger.info(f"Starting validation conversation for project '{project_name}' by user {current_user.username}")

        async def generate_validation_stream():
            import io
            import contextlib

            try:
                # Get Claude options
                api_key = get_anthropic_api_key()
                if not api_key:
                    yield f"data: {json.dumps({'type': 'error', 'message': 'CSDKAI_ANTHROPIC_API_KEY (or ANTHROPIC_API_KEY) environment variable not set'})}\n\n"
                    yield "data: [DONE]\n\n"
                    return

                # Always start fresh validation sessions (no session resumption)
                claude_options, error = get_validation_claude_options(session_id=None)
                if error:
                    yield f"data: {json.dumps({'type': 'error', 'message': error})}\n\n"
                    yield "data: [DONE]\n\n"
                    return

                yield f"data: {json.dumps({'type': 'log', 'message': f'Validating description for project: {project_name}'})}\n\n"

                # Capture stdout to stream output
                stdout_capture = io.StringIO()

                # Run validation with stdout capture
                with contextlib.redirect_stdout(stdout_capture):
                    result = await validate_description(
                        claude_options=claude_options,
                        project_name=project_name,
                        initial_description=body.description,
                        user_workspace=user_workspace_path,
                        conversation_messages=body.conversation_history
                    )

                # Get captured output
                captured_output = stdout_capture.getvalue()

                # Debug logging - dump full response to file for analysis
                agent_response = result.get('agent_response', '')
                logger.info(f"Validation result: success={result.get('success')}, validation_complete={result.get('validation_complete')}, agent_response_len={len(agent_response)}, captured_output_len={len(captured_output)}")
                import datetime
                debug_path = f"/tmp/validation_response_{datetime.datetime.now().strftime('%H%M%S')}.txt"
                with open(debug_path, 'w') as f:
                    f.write(f"=== AGENT RESPONSE ({len(agent_response)} chars) ===\n")
                    f.write(agent_response)
                    f.write(f"\n\n=== CAPTURED STDOUT ({len(captured_output)} chars) ===\n")
                    f.write(captured_output)
                logger.info(f"Full response dumped to {debug_path}")

                # Stream captured output line by line (preserve blank lines for formatting)
                for line in captured_output.splitlines():
                    yield f"data: {json.dumps({'type': 'log', 'message': line})}\n\n"

                # Send completion status based on result, including the full agent response
                # so the frontend doesn't depend on reconstructing it from individual log messages
                if result.get("success"):
                    if result.get("validation_complete"):
                        yield f"data: {json.dumps({'type': 'complete', 'status': 'validation_complete', 'message': 'Validation completed successfully', 'agent_response': result.get('agent_response', ''), 'enhanced_description': result.get('enhanced_description', '')})}\n\n"
                    else:
                        yield f"data: {json.dumps({'type': 'continue', 'status': 'needs_more_info', 'message': 'More information needed', 'agent_response': result.get('agent_response', '')})}\n\n"
                else:
                    error_msg = result.get("error", "Validation failed")
                    yield f"data: {json.dumps({'type': 'error', 'status': 'error', 'message': error_msg})}\n\n"

                yield "data: [DONE]\n\n"

            except Exception as e:
                error_detail = log_and_format_error(e, "Error during validation")
                yield f"data: {json.dumps({'type': 'error', 'message': error_detail})}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(
            generate_validation_stream(),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        error_msg = log_and_format_error(e, "Error during validation")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg
        )


@app.delete('/validation-session/{project_name}')
async def clear_validation_session(project_name: str, current_user: UserSession = Depends(get_current_user)):
    """
    Clear the validation session for a project, allowing a fresh start.
    Note: Validation sessions no longer use resumption, but endpoint kept for frontend compatibility.
    """
    return {"success": True, "message": "Validation session cleared"}


@app.post('/smart-connector-interaction')
@limiter.limit("10/minute")
async def smart_connector_interaction(request: Request, body: SmartConnectorRequest, current_user: UserSession = Depends(get_current_user)):
    """Smart connector interaction with AI (rate limited: 10/min)"""
    project_name = body.project_name
    user_message = body.user_message

    # Get user workspace directory
    username = current_user.username
    user_workspace_dir = BASE_DIR / username

    # Validate project exists
    project_dir = user_workspace_dir / "connectors" / project_name
    project_state_dir = user_workspace_dir / "projects" / project_name
    project_state_dir.mkdir(parents=True, exist_ok=True)
    if not project_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{project_name}' not found"
        )

    connector_file = project_dir / "connector.py"
    if not connector_file.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"connector.py not found in project '{project_name}'"
        )

    async def generate_smart_stream():
        try:
            # Save user message to chat history
            user_chat_message = {
                "type": "user",
                "text": user_message,
                "timestamp": datetime.now().isoformat()
            }
            save_connector_chat_message(username, project_name, user_chat_message)

            # Run unified interaction process using _interact.py (handles both analysis and revision)
            interact_script_path = Path(__file__).parent / "_interact.py"

            # Get API key from environment
            api_key = get_anthropic_api_key()
            if not api_key:
                yield json.dumps({"type": "error", "message": "CSDKAI_ANTHROPIC_API_KEY (or ANTHROPIC_API_KEY) environment variable not set"}) + '\n'
                return

            # Load existing session ID from project state directory
            existing_session_id = load_session_id(project_state_dir) or ""

            # Note: Do NOT pre-create credentials file here (unlike debug-connector-stream)
            # _interact.py handles its own CONFIG_REVIEW_REQUIRED flow for every test run

            # Build command with optional session_id
            cmd_args = [
                sys.executable, str(interact_script_path),
                project_name,
                user_message,  # Plain string, not JSON-encoded
                str(user_workspace_dir)
            ]
            if existing_session_id:
                cmd_args.append(existing_session_id)

            process = subprocess.Popen(
                cmd_args,
                cwd=Path(__file__).parent,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=0,
                env={**os.environ, 'PYTHONUNBUFFERED': '1', 'CSDKAI_ANTHROPIC_API_KEY': api_key},
                preexec_fn=os.setsid if os.name != 'nt' else None
            )

            # Store process for potential cancellation
            process_key = f"{username}_{project_name}_interact"
            active_processes[process_key] = process

            # Log process lifecycle
            print(f"Started unified interaction process {process.pid} for {process_key}")

            # Use the same non-blocking streaming approach as other endpoints
            import queue
            import threading

            # Create a queue to capture output in real-time
            output_queue = queue.Queue()
            new_session_id = None  # Capture new session ID from output

            def stream_output(pipe, output_queue, prefix=""):
                """Stream output from subprocess pipe to queue"""
                if pipe is None:
                    return
                try:
                    for line in iter(pipe.readline, ''):
                        if line:
                            line_stripped = line.rstrip()
                            if line_stripped.strip():
                                output_queue.put(f"{prefix}{line_stripped}")
                except Exception as e:
                    logger.error(f"Error reading subprocess output: {str(e)}")
                    output_queue.put("Error reading process output")
                finally:
                    if pipe:
                        pipe.close()

            # Start threads to capture stdout and stderr
            stdout_thread = threading.Thread(
                target=stream_output,
                args=(process.stdout, output_queue, "")
            )
            stderr_thread = threading.Thread(
                target=stream_output,
                args=(process.stderr, output_queue, "ERROR: ")
            )

            stdout_thread.start()
            stderr_thread.start()

            try:
                # Stream output as it comes (non-blocking)
                collected_logs = []  # Collect logs for chat history
                initial_ai_message_saved = False  # Track if we've saved initial AI message
                while True:
                    # Check if process is still running
                    return_code = process.poll()

                    # Get output from queue with non-blocking check
                    try:
                        line = output_queue.get_nowait()  # Non-blocking

                        # Check for SESSION_ID prefixed messages and capture session
                        if line.startswith("SESSION_ID:"):
                            try:
                                new_session_id = line.split(":", 1)[1].strip()
                                # Don't yield to client or add to chat history
                                continue
                            except Exception:
                                pass

                        # Check for CONFIG_REVIEW_REQUIRED message
                        if line.startswith("CONFIG_REVIEW_REQUIRED:"):
                            try:
                                config_data = line.split(":", 1)[1].strip()
                                config_json = json.loads(config_data)

                                # Merge cached credentials into config (pre-fill popup with actual values)
                                credentials_key = f"{current_user.session_token}:{project_name}"
                                merged_config = config_json['configuration'].copy()

                                # Try memory cache for credentials
                                cached_creds = get_credentials_for_project(
                                    current_user.session_token, project_name
                                )

                                if cached_creds:
                                    # Replace "****" with actual cached values for pre-filling
                                    for key, value in merged_config.items():
                                        if value == "****":
                                            if key in cached_creds:
                                                merged_config[key] = cached_creds[key]
                                            else:
                                                # No cached credential - show empty field
                                                merged_config[key] = ""
                                    # Clear memory cache AFTER merging (forces polling to wait for new submission)
                                    with credentials_lock:
                                        if credentials_key in session_credentials:
                                            del session_credentials[credentials_key]
                                else:
                                    # Replace "****" with empty strings since no cached credentials exist
                                    for key, value in merged_config.items():
                                        if value == "****":
                                            merged_config[key] = ""

                                # Read sensitivity metadata if it exists (same pattern as debug endpoint)
                                metadata_file = project_dir / ".config_metadata.json"
                                sensitive_fields = []
                                if metadata_file.exists():
                                    try:
                                        with open(metadata_file) as f:
                                            metadata = json.load(f)
                                            sensitive_fields = metadata.get("sensitive_fields", [])
                                    except Exception:
                                        # Fall back to empty list - frontend will auto-detect from field names
                                        pass

                                # Clear any stale cancellation flags before showing popup
                                with cancellation_lock:
                                    if credentials_key in session_cancellations:
                                        del session_cancellations[credentials_key]

                                # Yield config review event to frontend with merged values AND sensitive fields
                                config_review_response = {
                                    "type": "config_review",
                                    "configuration": merged_config,
                                    "sensitive_fields": sensitive_fields,
                                    "timestamp": datetime.now().isoformat()
                                }
                                yield f"data: {json.dumps(config_review_response)}\n\n"

                                # Wait for credentials from session (polling will wait since cache was cleared)
                                credentials_provided = False
                                poll_count = 0
                                while not credentials_provided:
                                    await asyncio.sleep(0.1)  # Async sleep for interact
                                    poll_count += 1

                                    # Check if user cancelled (closed popup)
                                    with cancellation_lock:
                                        cancelled = session_cancellations.get(credentials_key, False)
                                    if cancelled:
                                        # Clear cancellation flag
                                        with cancellation_lock:
                                            del session_cancellations[credentials_key]
                                        # Send empty credentials to unblock subprocess, it will skip testing
                                        process.stdin.write("{}\n")
                                        process.stdin.flush()
                                        yield f"data: {json.dumps({'type': 'message', 'content': '⏭️  Configuration review skipped by user'})}\n\n"
                                        credentials_provided = True
                                        continue

                                    # Check if credentials were submitted for this session
                                    with credentials_lock:
                                        session_creds = session_credentials.get(credentials_key, {})
                                    if session_creds:
                                        # Send credentials to interact process stdin (wrapped in {"credentials": {...}} format)
                                        creds_json = json.dumps({"credentials": session_creds})
                                        process.stdin.write(creds_json + '\n')
                                        process.stdin.flush()
                                        credentials_provided = True
                                # Don't collect for chat history
                                continue
                            except Exception as e:
                                print(f"Warning: Could not parse CONFIG_REVIEW_REQUIRED: {e}")
                                pass

                        # Check for TEST_LOG prefixed messages and route to test_log type
                        if line.startswith("TEST_LOG:"):
                            # Parse TEST_LOG:LEVEL:message format
                            try:
                                parts = line.split(":", 2)  # Split into at most 3 parts
                                if len(parts) >= 3:
                                    test_level = parts[1].strip()
                                    test_message = parts[2].strip()
                                    # Route to test_log type for Logs tab (don't add to chat)
                                    yield f"data: {json.dumps({'type': 'test_log', 'level': test_level, 'message': test_message})}\n\n"
                                    # Don't collect for chat history - logs tab only
                                    continue
                            except Exception:
                                # Fallback to regular processing if parsing fails
                                pass

                        # Parse log level from line content (same as other endpoints)
                        if line.startswith("ERROR:") or "❌" in line:
                            level = "ERROR"
                            message = line.replace("ERROR: ", "")
                        elif "⚠️" in line or "WARNING" in line:
                            level = "WARNING"
                            message = line
                        elif "✅" in line or "SUCCESS" in line or "💡" in line or "🔄" in line or "🧠" in line:
                            level = "SUCCESS"
                            message = line
                        else:
                            level = "INFO"
                            message = line

                        # Collect logs for chat history
                        collected_logs.append(f"[{level}] {message}")

                        # Save progress incrementally every 10 log entries
                        if len(collected_logs) % 10 == 0 or not initial_ai_message_saved:
                            try:
                                ai_message = {
                                    "type": "ai",
                                    "text": "\n".join(collected_logs),
                                    "timestamp": datetime.now().isoformat(),
                                    "responseTime": 0,
                                    "status": "in_progress"  # Mark as in progress
                                }
                                save_connector_chat_message(username, project_name, ai_message, update_last_ai_message=initial_ai_message_saved)
                                initial_ai_message_saved = True
                            except Exception as e:
                                print(f"Warning: Could not save incremental chat history: {e}")

                        # Create streaming response with same format as other endpoints
                        response_data = {
                            "type": "log",
                            "level": level,
                            "message": message,
                            "timestamp": datetime.now().isoformat()
                        }

                        yield f"data: {json.dumps(response_data)}\n\n"

                    except queue.Empty:
                        # No output available, check if process is done
                        if return_code is not None:
                            break

                        # Small delay to prevent busy waiting
                        await asyncio.sleep(0.1)

                # Wait for threads to complete
                stdout_thread.join(timeout=5)
                stderr_thread.join(timeout=5)

                # Get final return code
                return_code = process.returncode if process.returncode is not None else process.poll()

                # Persist new session ID to project state directory
                if new_session_id:
                    save_session_id(project_state_dir, new_session_id)

                # Update final AI completion message to chat history with collected logs
                if collected_logs:
                    completion_status = "✅ Interaction completed successfully!" if return_code == 0 else "❌ Interaction failed"
                    ai_message = {
                        "type": "ai",
                        "text": "\n".join(collected_logs) + f"\n\n{completion_status}",
                        "timestamp": datetime.now().isoformat(),
                        "responseTime": 0,  # We don't track response time for interactions
                        "status": "completed" if return_code == 0 else "error"
                    }
                    save_connector_chat_message(username, project_name, ai_message, update_last_ai_message=initial_ai_message_saved)
                else:
                    # Fallback if no logs were collected
                    completion_status = "✅ Interaction completed successfully!" if return_code == 0 else "❌ Interaction failed"
                    ai_message = {
                        "type": "ai",
                        "text": completion_status,
                        "timestamp": datetime.now().isoformat(),
                        "responseTime": 0,  # We don't track response time for interactions
                        "status": "completed" if return_code == 0 else "error"
                    }
                    save_connector_chat_message(username, project_name, ai_message, update_last_ai_message=initial_ai_message_saved)

                # Send completion status
                final_response = {
                    "type": "complete",
                    "success": return_code == 0,
                    "return_code": return_code,
                    "timestamp": datetime.now().isoformat()
                }
                yield f"data: {json.dumps(final_response)}\n\n"

            finally:
                # Clean up process from active processes
                if process_key in active_processes:
                    del active_processes[process_key]

                # Ensure process is terminated gracefully
                if process.poll() is None:
                    print(f"Cleaning up unified interaction process {process.pid} for {process_key}")
                    terminate_process_gracefully(process, timeout=5)

        except Exception as e:
            error_detail = log_and_format_error(e, "Error during interaction")
            # Save interaction logs to chat history even on exception
            if 'collected_logs' in locals() and collected_logs:
                ai_message = {
                    "type": "ai",
                    "text": "\n".join(collected_logs) + f"\n\n❌ {error_detail}",
                    "timestamp": datetime.now().isoformat(),
                    "responseTime": 0,
                    "status": "error"
                }
                save_connector_chat_message(username, project_name, ai_message, update_last_ai_message='initial_ai_message_saved' in locals() and initial_ai_message_saved)

            error_response = {
                "type": "error",
                "message": error_detail,
                "timestamp": datetime.now().isoformat()
            }
            yield f"data: {json.dumps(error_response)}\n\n"

    return StreamingResponse(
        generate_smart_stream(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )

# Database Viewer Endpoints

class DatabaseViewerRequest(BaseModel):
    username: str
    project_name: str

    @validator('project_name')
    def validate_project_name_format(cls, v):
        if not v or not ALLOWED_PROJECT_NAME_PATTERN.match(v):
            raise ValueError('Invalid project name format')
        return v

class CustomQueryRequest(BaseModel):
    username: str
    project_name: str
    query: str

    @validator('project_name')
    def validate_project_name_format(cls, v):
        if not v or not ALLOWED_PROJECT_NAME_PATTERN.match(v):
            raise ValueError('Invalid project name format')
        return v

# Table name pattern for SQL injection prevention
TABLE_NAME_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)?$')

def find_warehouse_db(username: str, project_name: str) -> str:
    """Find warehouse.db file for a given project with path traversal protection."""
    # Validate project_name format
    if not ALLOWED_PROJECT_NAME_PATTERN.match(project_name):
        raise ValueError(f"Invalid project name format: {project_name}")

    user_workspace = get_user_workspace(username)
    project_dir = Path(user_workspace["connectors"]) / project_name

    # Containment check: ensure resolved path is under user's workspace
    resolved = project_dir.resolve()
    workspace_base = Path(user_workspace["connectors"]).resolve()
    if not str(resolved).startswith(str(workspace_base) + os.sep) and resolved != workspace_base:
        raise ValueError("Path traversal detected")

    warehouse_db_path = project_dir / "files" / "warehouse.db"
    return str(warehouse_db_path)

def sanitize_for_json(data):
    """
    Sanitize data for JSON serialization by replacing NaN/Inf with None.
    Handles nested dicts and lists.
    """
    import math

    if isinstance(data, dict):
        return {k: sanitize_for_json(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_for_json(item) for item in data]
    elif isinstance(data, float):
        if math.isnan(data) or math.isinf(data):
            return None
        return data
    else:
        return data

def get_user_tables(conn):
    """Get all user tables as (schema, table, full_path)."""
    try:
        query = '''
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_type = 'BASE TABLE'
                AND table_schema NOT IN ('information_schema', 'pg_catalog')
            ORDER BY table_schema, table_name
        '''
        rows = conn.execute(query).fetchall()
        return [(schema, table, f"{schema}.{table}") for schema, table in rows]
    except Exception:
        # Fallback for DuckDB if information_schema doesn't work as expected
        try:
            query = "SHOW TABLES"
            rows = conn.execute(query).fetchall()
            return [("main", table[0], f"main.{table[0]}") for table in rows]
        except Exception:
            return []

@app.post('/database/check')
async def check_database_exists(request: DatabaseViewerRequest, current_user: UserSession = Depends(get_current_user)):
    """Check if warehouse.db exists for the project"""
    # Ensure user can only access their own data
    if request.username != current_user.username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You can only access your own data"
        )

    try:
        warehouse_db_path = find_warehouse_db(request.username, request.project_name)
        exists = Path(warehouse_db_path).exists()

        if not exists:
            return {"success": False, "message": "warehouse.db not found"}

        # Try to connect to verify it's a valid database
        try:
            with duckdb.connect(warehouse_db_path, read_only=True) as conn:
                tables = get_user_tables(conn)
                return {
                    "success": True,
                    "exists": True,
                    "tables": [{"schema": schema, "table": table, "full_name": full_name} for schema, table, full_name in tables]
                }
        except Exception as e:
            logger.error(f"Database connection failed: {str(e)}")
            return {"success": False, "message": "Database connection failed. Please ensure the database file is valid."}

    except Exception as e:
        logger.error(f"Error checking database: {str(e)}")
        return {"success": False, "message": "An error occurred while checking the database."}

@app.post('/database/table-data')
async def get_table_data(request: dict, current_user: UserSession = Depends(get_current_user)):
    """Get table data preview and structure"""
    try:
        username = request.get('username')
        project_name = request.get('project_name')
        table_name = request.get('table_name')

        if not all([username, project_name, table_name]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing required fields: username, project_name, table_name"
            )

        # Validate project_name format to prevent path traversal
        if not ALLOWED_PROJECT_NAME_PATTERN.match(project_name):
            return {"success": False, "message": "Invalid project name format"}

        # Ensure user can only access their own data
        if username != current_user.username:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You can only access your own data"
            )

        # Validate table_name format to prevent SQL injection
        if not TABLE_NAME_PATTERN.match(table_name):
            return {"success": False, "message": "Invalid table name format"}

        warehouse_db_path = find_warehouse_db(username, project_name)
        if not Path(warehouse_db_path).exists():
            return {"success": False, "message": "warehouse.db not found"}

        with duckdb.connect(warehouse_db_path, read_only=True) as conn:
            # Handle schema.table names properly (already validated by regex)
            if '.' in table_name:
                table_ref = table_name
            else:
                table_ref = f'"{table_name}"'

            # Data preview
            preview_df = conn.execute(f'SELECT * FROM {table_ref} LIMIT 10').df()
            preview_data = sanitize_for_json(preview_df.to_dict('records'))

            # Structure info
            columns_info = conn.execute(f'DESCRIBE {table_ref}').fetchdf()
            total_rows = conn.execute(f'SELECT COUNT(*) FROM {table_ref}').fetchone()[0]

            structure = {
                "table_name": table_name,
                "total_rows": total_rows,
                "total_columns": len(columns_info),
                "columns": sanitize_for_json(columns_info.to_dict('records'))
            }

            return {
                "success": True,
                "preview": preview_data,
                "structure": structure,
                "default_query": f'SELECT * FROM {table_ref} LIMIT 10;'
            }

    except Exception as e:
        logger.error(f"Error getting table data: {str(e)}")
        return {"success": False, "message": "Failed to load table data."}

@app.post('/database/custom-query')
async def execute_custom_query(request: CustomQueryRequest, current_user: UserSession = Depends(get_current_user)):
    """Execute custom SQL query"""
    # Ensure user can only access their own data
    if request.username != current_user.username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You can only access your own data"
        )

    try:
        warehouse_db_path = find_warehouse_db(request.username, request.project_name)
        if not Path(warehouse_db_path).exists():
            return {"success": False, "message": "warehouse.db not found"}

        query = request.query.strip()
        if not query:
            return {"success": False, "message": "Please enter a SQL query"}

        # Normalize query for security checks: remove comments, collapse whitespace
        import re
        # Remove SQL comments (-- and /* */)
        query_normalized = re.sub(r'--.*?(?:\n|$)', ' ', query)
        query_normalized = re.sub(r'/\*.*?\*/', ' ', query_normalized, flags=re.DOTALL)
        # Collapse whitespace
        query_normalized = ' '.join(query_normalized.split())

        # Basic security check - only allow SELECT statements
        if not query_normalized.upper().strip().startswith('SELECT'):
            return {"success": False, "message": "Only SELECT queries are allowed"}

        # Block multiple statements (prevent injection via semicolons)
        if ';' in query_normalized:
            return {"success": False, "message": "Multiple SQL statements are not allowed"}

        # Block dangerous DuckDB functions that can read arbitrary files
        # Use word boundary matching to prevent bypass via obfuscation
        DANGEROUS_PATTERNS = [
            # File reading functions
            r'\bread_csv\b', r'\bread_csv_auto\b', r'\bread_json\b', r'\bread_json_auto\b',
            r'\bread_parquet\b', r'\bread_text\b', r'\bread_blob\b',
            # File system functions
            r'\bglob\b', r'\blist_files\b', r'\blist_dir\b',
            # External access (URLs)
            r'https?://', r's3://', r'gcs://', r'file://',
            # Data export
            r'\bcopy\b', r'\bexport\b', r'\bimport\b',
            # Database attachment
            r'\battach\b', r'\bdetach\b',
            # Extension loading
            r'\bload\b', r'\binstall\b',
            # System commands
            r'\bpragma\b', r'\bset\b',
            # Additional dangerous functions
            r'\bhttpfs\b', r'\bquery_table\b', r'\bfrom_csv\b', r'\bfrom_json\b',
        ]
        query_lower = query_normalized.lower()
        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                return {"success": False, "message": "Query contains disallowed function or keyword"}

        with duckdb.connect(warehouse_db_path, read_only=True) as conn:
            df = conn.execute(query).df()
            result_data = sanitize_for_json(df.to_dict('records'))

            return {
                "success": True,
                "result": result_data,
                "row_count": len(result_data),
                "column_names": list(df.columns)
            }

    except Exception as e:
        logger.error(f"Error executing query: {str(e)}")
        return {"success": False, "message": "Query failed. Please check your SQL syntax."}

@app.post('/analyze-error')
def analyze_error(request: dict, current_user: UserSession = Depends(get_current_user)):
    """
    Analyze error logs to classify error type and provide intelligent guidance
    """
    try:
        log_content = request.get('log_content', '')
        project_name = request.get('project_name', '')
        
        if not log_content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="log_content is required"
            )

        # Check if this is a first run (no successful debug yet)
        # We use .run_success marker (not warehouse.db which could exist from uploads)
        is_first_run = False
        if project_name:
            user_workspace = get_user_workspace(current_user.username)
            run_success_marker = Path(user_workspace["connectors"]) / project_name / ".run_success"
            is_first_run = not run_success_marker.exists()

        # Use the smart error classification
        error_analysis = classify_error_type(log_content, is_first_run=is_first_run)

        # Add context about the project
        error_analysis['project_name'] = project_name
        error_analysis['timestamp'] = datetime.now().isoformat()
        
        # Log the analysis for debugging
        logger.info(f"Error analysis for project '{project_name}' by user {current_user.username}: {error_analysis['type']} - {error_analysis['category']}")
        
        return {
            "success": True,
            "analysis": error_analysis
        }
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = log_and_format_error(e, "Error during error analysis")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg
        )

# Helper functions for deploy functionality
def find_connector_directory(username: str, project_name: str) -> Path:
    """Find the connector directory for a given project."""
    user_workspace = get_user_workspace(username)
    return Path(user_workspace["connectors"]) / project_name

def find_config_file(username: str, project_name: str) -> Optional[Path]:
    """Find the configuration.json file for a project."""
    config_path = find_connector_directory(username, project_name) / "configuration.json"
    return config_path if config_path.exists() else None

def extract_connector_url(output: str) -> Optional[str]:
    """Extract the connector URL from the deployment output."""
    import re
    pattern = r'https://fivetran\.com/dashboard/connectors/[^/\s]+/status'
    match = re.search(pattern, output)
    return match.group(0) if match else None

@app.post('/deploy-connector')
async def deploy_connector_stream(
    request: dict,
    current_user: UserSession = Depends(get_current_user)
):
    """Deploy a connector to Fivetran using the CLI."""
    try:
        # Extract parameters
        project_name = request.get('project_name', '').strip()
        connector_name = request.get('connector_name', '').strip()
        destination_name = request.get('destination_name', '').strip()
        api_key = request.get('api_key', '').strip()
        include_config = request.get('include_config', True)
        
        # Validate required parameters
        if not project_name:
            raise HTTPException(status_code=400, detail="Project name is required")
        if not connector_name:
            raise HTTPException(status_code=400, detail="Connector name is required")
        if not destination_name:
            raise HTTPException(status_code=400, detail="Destination name is required")
        if not api_key:
            raise HTTPException(status_code=400, detail="API key is required")

        # Validate project name format (security)
        if '..' in project_name or '/' in project_name or '\\' in project_name:
            raise HTTPException(status_code=400, detail="Invalid project name")

        # Validate connector name format
        if not validate_project_name(connector_name):
            raise HTTPException(
                status_code=400,
                detail="Invalid connector name. Must start with a letter or underscore, and can only contain lowercase letters, numbers, and underscores"
            )
        
        # Find connector directory
        connector_dir = find_connector_directory(current_user.username, project_name)
        if not connector_dir.exists():
            raise HTTPException(status_code=404, detail=f"Project '{project_name}' not found")
        
        # Check if connector.py exists
        connector_file = connector_dir / "connector.py"
        if not connector_file.exists():
            raise HTTPException(status_code=404, detail="No connector.py found in the project")
        
        # Check for configuration file
        config_file = find_config_file(current_user.username, project_name)

        # Venv directory path (will be checked/created in the streaming function)
        venv_dir = connector_dir / "venv"

        logger.info(f"Starting deployment for project '{project_name}' by user {current_user.username}")

        async def generate_deployment_stream():
            """Generate deployment output stream."""
            import queue
            import threading
            import sys
            import asyncio

            # Initialize metadata hiding variables (used in finally block)
            metadata_file = connector_dir / ".config_metadata.json"
            metadata_backup = connector_dir / ".config_metadata.json.deploy_backup"
            metadata_hidden = False

            try:
                # Save user deployment request to chat history
                user_message = {
                    "type": "user",
                    "text": f"Deploy connector: {connector_name} to {destination_name}",
                    "timestamp": datetime.now().isoformat()
                }
                save_connector_chat_message(current_user.username, project_name, user_message)

                yield f"data: 🚀 Starting deployment for connector: {connector_name}\n\n"
                await asyncio.sleep(0)
                yield f"data: 📁 Working directory: {connector_dir}\n\n"
                await asyncio.sleep(0)
                yield f"data: {'-' * 50}\n\n"
                await asyncio.sleep(0)

                # Ensure virtual environment exists (create if missing) using uv
                if not venv_dir.exists():
                    yield f"data: 📦 Virtual environment not found, creating one...\n\n"
                    await asyncio.sleep(0)
                    yield f"data:    (This is a one-time setup for this connector)\n\n"
                    await asyncio.sleep(0)

                    # Create venv using uv (uses shared cache, default Python)
                    result = subprocess.run(["uv", "venv", str(venv_dir)],
                                          capture_output=True, text=True, timeout=60)
                    if result.returncode != 0:
                        yield f"data: ❌ Failed to create virtual environment: {result.stderr}\n\n"
                        await asyncio.sleep(0)
                        return

                    yield f"data: ✅ Virtual environment created\n\n"
                    await asyncio.sleep(0)

                    # Install requirements.txt if exists using uv pip
                    requirements_path = connector_dir / "requirements.txt"
                    venv_python = venv_dir / "bin" / "python"
                    if requirements_path.exists():
                        yield f"data: 📦 Installing dependencies from requirements.txt...\n\n"
                        await asyncio.sleep(0)
                        install_result = subprocess.run(["uv", "pip", "install", "-r", str(requirements_path), "--python", str(venv_python)],
                                                       capture_output=True, text=True, timeout=300)
                        if install_result.returncode != 0:
                            yield f"data: ❌ Failed to install requirements: {install_result.stderr}\n\n"
                            await asyncio.sleep(0)
                            return
                        yield f"data: ✅ Dependencies installed\n\n"
                        await asyncio.sleep(0)

                    # Install fivetran_connector_sdk using uv pip
                    yield f"data: 📦 Installing fivetran_connector_sdk for deployment...\n\n"
                    await asyncio.sleep(0)
                    sdk_result = subprocess.run(["uv", "pip", "install", "fivetran_connector_sdk", "--python", str(venv_python)],
                                               capture_output=True, text=True, timeout=120)
                    if sdk_result.returncode != 0:
                        yield f"data: ❌ Failed to install fivetran_connector_sdk: {sdk_result.stderr}\n\n"
                        await asyncio.sleep(0)
                        return
                    yield f"data: ✅ fivetran_connector_sdk installed\n\n"
                    await asyncio.sleep(0)
                    yield f"data: {'-' * 50}\n\n"
                    await asyncio.sleep(0)

                # Load decrypted config into memory (never written to disk)
                decrypted_config = None
                config_pipe = None

                if config_file and include_config:
                    yield f"data: 🔐 Preparing configuration...\n\n"
                    await asyncio.sleep(0)

                    # Load and decrypt config into memory
                    decrypted_config = load_decrypted_config(connector_dir, current_user.username)
                    yield f"data: ✅ Configuration prepared\n\n"
                    await asyncio.sleep(0)

                # Use absolute path to fivetran from connector's venv to bypass pyenv shims
                fivetran_cmd = (venv_dir / "bin" / "fivetran").resolve()
                if not fivetran_cmd.exists():
                    yield f"data: ❌ fivetran executable not found in venv: {fivetran_cmd}\n\n"
                    return

                # Construct the deployment command (API key passed via env var to avoid leaking in process listings)
                # Always use --force to auto-answer confirmation prompts (webapp is non-interactive)
                # Note: --force only skips Yes/No prompts, actual errors (invalid API key, etc.) still fail
                command_parts = [str(fivetran_cmd), 'deploy',
                                '--destination', destination_name,
                                '--connection', connector_name,
                                '--force']

                # Add configuration via named pipe (stays in memory, never on disk)
                if config_file and include_config and decrypted_config:
                    config_pipe = ConfigPipe(connector_dir, decrypted_config)
                    pipe_path = config_pipe.__enter__()
                    command_parts.extend(['--configuration', pipe_path.name])

                # Display command (API key is in env var, not visible in process listings)
                yield f"data: 🔧 Command: {' '.join(command_parts)}\n\n"
                yield f"data: {'-' * 50}\n\n"
                yield f"data: 🔄 Running deployment command...\n\n"
                
                # Set environment variables to use connector's virtual environment
                env = os.environ.copy()
                env['PATH'] = f"{venv_dir / 'bin'}:{env['PATH']}"  # Prepend venv bin to PATH
                env['VIRTUAL_ENV'] = str(venv_dir)  # Set VIRTUAL_ENV
                env['PYTHONUNBUFFERED'] = '1'  # Force immediate output flushing
                env['FIVETRAN_API_KEY'] = api_key  # Pass API key via env var (not CLI args) to avoid leaking in ps aux
                
                # Create a queue to capture output in real-time
                output_queue = queue.Queue()

                def stream_output(pipe, output_queue, prefix=""):
                    """Stream output from subprocess pipe to queue"""
                    try:
                        for line in iter(pipe.readline, ''):
                            if line:
                                line_stripped = line.rstrip()
                                if line_stripped.strip():
                                    output_queue.put(f"{prefix}{line_stripped}")
                    except Exception as e:
                        logger.error(f"Error reading subprocess output: {str(e)}")
                        output_queue.put("Error reading process output")
                    finally:
                        pipe.close()

                # Temporarily hide internal metadata files from deployment
                # (these are webapp-internal and shouldn't be deployed to Fivetran)
                if metadata_file.exists():
                    try:
                        metadata_file.rename(metadata_backup)
                        metadata_hidden = True
                    except Exception as e:
                        logger.warning(f"Could not hide metadata file during deployment: {e}")

                # Create subprocess with proper working directory
                # stdin=DEVNULL prevents prompt_toolkit EOFError when fivetran CLI
                # tries to read interactive input (there's no TTY in web server context)
                process = subprocess.Popen(
                    command_parts,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=str(connector_dir),
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                    env=env,
                    preexec_fn=os.setsid if os.name != 'nt' else None
                )

                # Start threads to capture stdout and stderr
                stdout_thread = threading.Thread(
                    target=stream_output,
                    args=(process.stdout, output_queue, "")
                )
                stderr_thread = threading.Thread(
                    target=stream_output,
                    args=(process.stderr, output_queue, "ERROR: ")
                )
                
                stdout_thread.start()
                stderr_thread.start()
                
                # Stream output as it comes
                while True:
                    # Check if process is still running
                    return_code = process.poll()
                    
                    # Get output from queue with non-blocking check
                    try:
                        line = output_queue.get_nowait()  # Non-blocking
                        yield f"data: {line}\n\n"
                    except queue.Empty:
                        # No output available, yield control
                        await asyncio.sleep(0.1)
                    
                    # Check if process finished and no more output
                    if return_code is not None:
                        # Process finished, collect any remaining output
                        remaining_output = []
                        while True:
                            try:
                                line = output_queue.get_nowait()
                                remaining_output.append(line)
                            except queue.Empty:
                                break
                        
                        # Yield any remaining output
                        for line in remaining_output:
                            yield f"data: {line}\n\n"
                        
                        break
                
                # Wait for threads to complete
                stdout_thread.join(timeout=5)
                stderr_thread.join(timeout=5)
                
                yield f"data: \n\n"
                yield f"data: {'=' * 50}\n\n"
                yield f"data: Process completed with exit code: {return_code}\n\n"
                
                if return_code == 0:
                    yield f"data: ✅ Deployment completed successfully!\n\n"

                    # Log successful deployment to CSV
                    from deployment_stats import log_successful_deployment
                    log_successful_deployment(
                        username=current_user.username,
                        project_name=project_name,
                        connector_name=connector_name,
                        destination_name=destination_name
                    )

                    # Save deployment success to chat history
                    ai_message = {
                        "type": "ai",
                        "text": "Deployment completed successfully",
                        "timestamp": datetime.now().isoformat(),
                        "responseTime": 0
                    }
                    save_connector_chat_message(current_user.username, project_name, ai_message)
                else:
                    yield f"data: ❌ Deployment failed with exit code: {return_code}\n\n"

                    # Save deployment failure to chat history
                    ai_message = {
                        "type": "ai",
                        "text": f"Deployment failed with exit code: {return_code}",
                        "timestamp": datetime.now().isoformat(),
                        "responseTime": 0
                    }
                    save_connector_chat_message(current_user.username, project_name, ai_message)

                # Cleanup config pipe (if used)
                if config_pipe:
                    config_pipe.__exit__(None, None, None)

            except FileNotFoundError:
                yield f"data: ❌ Error: 'fivetran' command not found. Please install the Fivetran CLI.\n\n"
                if config_pipe:
                    config_pipe.__exit__(None, None, None)
            except Exception as e:
                logger.error(f"Deployment error for user {current_user.username}: {str(e)}")
                yield f"data: ❌ A deployment error occurred. Please check the logs and try again.\n\n"
                if config_pipe:
                    config_pipe.__exit__(None, None, None)
            finally:
                # Restore hidden metadata file after deployment (success or failure)
                if metadata_hidden and metadata_backup.exists():
                    try:
                        metadata_backup.rename(metadata_file)
                    except Exception as e:
                        logger.warning(f"Could not restore metadata file after deployment: {e}")

            yield f"data: [DONE]\n\n"
        
        return StreamingResponse(
            generate_deployment_stream(),
            media_type="text/plain",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "text/event-stream"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = log_and_format_error(e, "Error during deployment")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_msg
        )
