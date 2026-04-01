# Claude Code Context

## Session Management Implementation

The application uses FastAPI with session token-based authentication. Each login creates a unique session token and maintains session state in the `active_sessions` dictionary with automatic expiration.

### Key Components

**Session Creation** (`main.py:201-215`):
```python
def create_session(username: str) -> str:
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
```

**Session Validation** (`main.py:217-237`):
```python
def get_session(session_token: str) -> Optional[UserSession]:
    if session_token not in active_sessions:
        return None
    
    session = active_sessions[session_token]
    
    # Check if session is expired
    if datetime.now() > session.expires_at:
        del active_sessions[session_token]
        return None
    
    return session
```

**Session Persistence** (`main.py:62-109`):
- Sessions saved to `sessions.json` file for persistence across restarts
- Automatic cleanup of expired sessions on load
- 48-hour session expiration for long-running generation jobs

### Recent Fixes

- **Session Token Security**: Implemented cryptographically secure session tokens with automatic expiration
- **Streaming Generation**: Real-time streaming output for connector generation using Server-Sent Events
- **Process Management**: Subprocess-based execution with proper cleanup and timeout handling
- **Tool Output Optimization**: Simplified tool output display (Read/Write show filenames, Grep/Glob show tool name only, TodoWrite hidden)
- **Error Classification**: Added early USER error detection for configuration issues before calling fixer agent
- **Timeout Standardization**: Standardized timeouts across all subprocess operations
- **Database Integration**: DuckDB-based warehouse.db validation and querying capabilities
- **Requirements Generation**: Switched to pipreqs for accurate dependency detection instead of AI guessing
- **Streaming Fixes**: Non-blocking output streaming with queue-based capture to prevent hangs
- **Path Security**: Enhanced path validation and sanitization to prevent directory traversal
- **Universal Configuration Verification**: Centralized credential checking in `_run.py` ensures all test runs verify credentials before execution
- **CONFIG_REVIEW_REQUIRED Protocol**: All streaming endpoints (generator auto-fix, debug auto-fix, interact) now support credential verification modal

### Configuration Verification System

**Centralized Credential Checking** (`_run.py:227-266`):
- Checks `configuration.json` for masked values ("****") before any test/run execution
- Emits `CONFIG_REVIEW_REQUIRED` message with configuration schema
- Waits for credentials via stdin, saves to temp file
- Applies to ALL scenarios: generation, fixing, revision, interactive chat, debug

**run_tester() Stdin Passthrough** (`_run.py:124-197`):
- Added `stdin=subprocess.PIPE` to support credential exchange
- Detects `CONFIG_REVIEW_REQUIRED` messages from subprocess
- Forwards credentials from parent process stdin to subprocess stdin
- Enables credential verification when fixer/interact agents call tests

**Streaming Endpoint Integration**:
1. **Generator Auto-Fix** (`main.py:1716-1742`): CONFIG_REVIEW_REQUIRED detection during automatic fix after generation failure
2. **Debug Auto-Fix** (`main.py:2386-2423`): CONFIG_REVIEW_REQUIRED detection during automatic fix after debug failure
3. **Interactive Chat** (`main.py:2859-2888`): CONFIG_REVIEW_REQUIRED detection when interact agent tests connector after code changes

All three endpoints:
- Poll `session_credentials` dictionary for submitted credentials
- Send credentials to subprocess via stdin pipe
- Resume execution after credentials received
- Trigger frontend modal via `config_review_required` event type

### Process Management

**Subprocess Execution** (`main.py:1193-1201`):
```python
process = subprocess.Popen(cmd,
                          stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE,
                          env=env,
                          cwd=str(app_dir),
                          text=True,
                          bufsize=1,
                          universal_newlines=True
                          )
```

**Active Process Tracking** (`main.py:56-57`):
```python
# Active generation processes storage
active_processes = {}
```

### Testing Infrastructure

**Automatic Testing Integration**:
- `_run.py`: Connector execution and validation script
- Auto-runs after successful generation/revision/fixing operations
- `/debug-connector-stream`: Real-time streaming debug endpoint

### Persistent History System

**Architecture** (`history_utils.py`):
- Each subagent maintains persistent conversation history across runs
- History stored in JSON format with metadata (timestamps, message counts)
- Automatic username extraction from workspace paths for organization

**Workspace Structure**:
```
workspaces/
├── {username}/
│   ├── connectors/     # Generated connector projects  
│   ├── history/        # Persistent agent conversation history
│   └── projects/       # Project metadata JSON files
```

**Key Functions**:
- `load_agent_history(username, agent_name)`: Load previous conversations
- `save_agent_history(username, agent_name, messages)`: Persist conversation state
- `message_to_dict()` / `dict_to_message_adapter()`: Serialize/deserialize Claude Code SDK messages
- `extract_username_from_user_dir()`: Parse username from workspace paths

**Message Serialization** (`history_utils.py:65-107`):
- Converts Claude Code SDK messages (AssistantMessage, UserMessage, ToolUseBlock, ToolResultBlock) to JSON
- Preserves tool correlation data for proper display formatting
- Handles TextBlock, ToolUseBlock, and ToolResultBlock content types

**Integration Points**:
- All subagent scripts (_generate.py, _fix_revise.py) use persistent history
- Conversation history passed to `format_message_for_display()` for proper tool identification
- History saved even on errors to maintain continuity

### Log Optimization

**Tool Output Formatting** (`message_utils.py`):
- Read tool shows excerpts instead of full content
- TodoWrite confirmations hidden, actual todo lists shown  
- Task tool output displays content directly without "🔧 Task:" prefix
- Enhanced message parsing and cleanup with proper newline spacing
- System reminder text filtered from user-visible output

### API Endpoints

**Authentication**:
```bash
POST /auth/login      # Login with Google OAuth
POST /auth/logout     # Invalidate session
POST /auth/refresh    # Extend session expiration
```

**Generation**:
```bash
POST /generate-connector-stream    # Real-time connector generation

POST /debug-connector-stream       # Real-time connector testing
```

### Authentication & Workspace Management

**Google OAuth Authentication**:
- Login via Google OAuth 2.0 with domain-based whitelisting
- Only @fivetran.com email addresses allowed (configurable via CSDKAI_ALLOWED_DOMAINS env var)
- Username auto-generated from email (john.doe@fivetran.com → john_doe)
- Bearer token authentication with automatic expiration
- Workspace auto-created on first login

**Security Features**:
- Google handles authentication security (2FA, password policies, etc)
- Cryptographically secure session tokens using `secrets.token_urlsafe(32)`
- Session persistence across server restarts via `sessions.json`
- User data isolation with workspace-based access control
- Path traversal protection and file validation
- Domain-based access control prevents unauthorized users

**Workspace Auto-Provisioning** (`main.py:330-337`):
- Auto-creates structured workspace directory: `workspaces/{username}/`
- Subdirectories: `connectors/`, `history/`, `projects/`
- User isolation prevents cross-user data access
- Project metadata stored in JSON format

### Subagent Timeout & Retry Improvements

**Test Script Timeout Optimization** (`_run.py:14-15`):
- TEST_TIME = 30 seconds for connector execution
- TESTER_PROCESS_TIMEOUT = 60 seconds total timeout
- Enhanced error messages for timeout scenarios

**Message Display Improvements** (`message_utils.py`):
- Fixed TodoWrite confirmation suppression - now shows actual task lists instead of generic messages
- Enhanced `format_todowrite_content()` to extract JSON todo data
- Added support for `activeForm` display for in-progress tasks
- Improved status emoji display: ⏳ pending, 🔄 in_progress, ✅ completed

**Fixing Agent Retry Logic** (`_fix_revise.py`):
- Intelligent error detection and classification system
- Smart early exit for non-code errors (credentials, network, permissions) 
- Automatic retry logic integrated with generation pipeline
- Environmental error detection prevents wasted retry attempts
- AI-based error classification (USER vs CODE types) instead of hardcoded patterns

**Tool Identification System** (`message_utils.py:205-289`):
- Correlates ToolUseBlock and ToolResultBlock via tool_use_id mapping
- Uses conversation history to identify tool names for proper display
- Handles all Claude Code SDK tools: Task, Read, Write, Edit, Bash, Grep, Glob, WebFetch, etc.
- Message adapter pattern converts stored history format to runtime objects

### Known Issues

- Monitor session persistence across server restarts in production
- API key exposure in .env file should be rotated regularly
- Large file uploads may exceed memory limits without streaming
- Subprocess execution without sandboxing presents security risks
- Test agents may hang on network-dependent operations despite timeout improvements
