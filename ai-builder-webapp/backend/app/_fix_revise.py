import json
import sys
import asyncio
import shutil
import stat
from datetime import datetime

from pathlib import Path
from _generate import get_claude_options
from prompt_utils import load_prompt_template
from config import CLAUDE_MODEL, FIXER_TOOLS, PERMISSION_MODE, ENV_ANTHROPIC_API_KEY, ENV_ANTHROPIC_API_KEY_FALLBACK
import os
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, AssistantMessage, TextBlock, ResultMessage, PermissionResultAllow, PermissionResultDeny
from _run import run_tester
from message_utils import format_message_for_display
from history_utils import get_connectors_dir


def create_file_access_validator(allowed_dir: Path):
    """Create a permission callback that restricts file access to allowed_dir."""
    async def validate_file_access(tool_name: str, tool_input: dict, context):
        """Validate that file operations only access files within allowed directory."""
        # Only validate file-access tools
        if tool_name not in ["Read", "Edit", "Glob", "Grep"]:
            return PermissionResultAllow()

        # Extract file path from tool input
        file_path = None
        if tool_name in ["Read", "Edit"]:
            file_path = tool_input.get("file_path")
        elif tool_name == "Glob":
            file_path = tool_input.get("path")
            if not file_path:
                return PermissionResultAllow()
        elif tool_name == "Grep":
            file_path = tool_input.get("path")
            if not file_path:
                return PermissionResultAllow()

        if not file_path:
            return PermissionResultAllow()

        try:
            requested_path = Path(file_path).resolve()
            allowed_path = allowed_dir.resolve()
            requested_path.relative_to(allowed_path)
            return PermissionResultAllow()
        except (ValueError, RuntimeError):
            return PermissionResultDeny(
                message=f"Access denied: {file_path} is outside the project directory",
                interrupt=True
            )

    return validate_file_access


def get_claude_options_for_fixer(api_key=None, model=None, project_dir=None, session_id=None):
    """Get Claude Code options specifically for fixer/reviser agents with secure tool set."""
    # Use provided key or fall back to environment variable
    key_to_use = api_key or os.getenv(ENV_ANTHROPIC_API_KEY) or os.getenv(ENV_ANTHROPIC_API_KEY_FALLBACK)

    if not key_to_use:
        return None, f"No API key provided and {ENV_ANTHROPIC_API_KEY} (or {ENV_ANTHROPIC_API_KEY_FALLBACK}) environment variable not found"

    # Default model
    if model is None:
        model = CLAUDE_MODEL

    try:
        # Set the API key as environment variable for claude-agent-sdk
        os.environ['ANTHROPIC_API_KEY'] = key_to_use

        # Create file access validator if project_dir is provided
        file_validator = create_file_access_validator(project_dir) if project_dir else None

        options = ClaudeAgentOptions(
            allowed_tools=FIXER_TOOLS,
            permission_mode=PERMISSION_MODE,
            model=model,
            resume=session_id,  # Resume generator's session if available
            cwd=project_dir,
            can_use_tool=file_validator
        )
        return options, None
    except Exception as e:
        return None, f"Error creating Claude Agent options: {str(e)}"


def reset_state(user_workspace: Path, project_name: str) -> int:
    files_dir = get_connectors_dir(user_workspace) / project_name / "files"
    if files_dir.exists():
        try:
            shutil.rmtree(files_dir)
            return 0
        except Exception as e:
            return -1
    else:
        return -2


def cleanup_temp_files(project_dir: Path):
    """Clean up any temporary files (named pipes)."""
    for temp_file in [".config_pipe"]:
        temp_path = project_dir / temp_file
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass


def save_credentials_to_config(project_dir: Path, credentials: dict, username: str):
    """Merge credentials into configuration.json and encrypt it.

    Args:
        project_dir: Path to the connector directory
        credentials: Dictionary of credential values to merge
        username: Username for encryption key derivation
    """
    config_file = project_dir / "configuration.json"

    # Read existing config template
    if config_file.exists():
        try:
            file_content = config_file.read_text()
            # Try JSON first (unencrypted template)
            try:
                config = json.loads(file_content)
            except json.JSONDecodeError:
                # Already encrypted - decrypt first
                import sys
                app_dir = Path(__file__).parent
                if str(app_dir) not in sys.path:
                    sys.path.insert(0, str(app_dir))
                from encryption import decrypt_config
                config = decrypt_config(username, file_content)
        except Exception:
            config = {}
    else:
        config = {}

    # Merge credentials into config
    config.update(credentials)

    # Encrypt and save
    import sys
    app_dir = Path(__file__).parent
    if str(app_dir) not in sys.path:
        sys.path.insert(0, str(app_dir))
    from encryption import encrypt_config
    encrypted = encrypt_config(username, config)
    config_file.write_text(encrypted)


async def main():
    # Initialize variables at function scope to avoid unbound warnings
    conversation_history = []

    project_name  = sys.argv[1]
    user_workspace = Path(sys.argv[2])
    error_msg = json.loads(sys.argv[3])
    session_id = sys.argv[4] if len(sys.argv) > 4 else None
    revision_instructions = sys.argv[5] if len(sys.argv) > 5 else None

    # Extract username from workspace path (e.g., "../workspaces/john_doe" -> "john_doe")
    username = user_workspace.name

    user_code_dir = get_connectors_dir(user_workspace)
    project_dir = user_code_dir / project_name

    if revision_instructions:
        print(f"Revision instructions: {revision_instructions}\n")
        print(f"\n🔄 Deploying revision agent...")
        prompt_template = load_prompt_template("REVISER_AGENT")
    else:
        print(f"\n🔧 Deploying fixer agent...")
        prompt_template = load_prompt_template("FIXER_AGENT")

    connector_file = project_dir / "connector.py"
    if not connector_file.exists():
        print(f"❌ connector.py not found in {project_dir}")
        cleanup_temp_files(project_dir)
        sys.exit(1)

    # Create backup of connector.py before making changes
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Create archive folder if it doesn't exist
    archive_dir = project_dir / "archive"
    archive_dir.mkdir(exist_ok=True)
    
    backup_file = archive_dir / f"connector.py.{timestamp}"
    try:
        shutil.copy2(connector_file, backup_file)
        print(f"📋 Created backup: archive/{backup_file.name}")
    except Exception as e:
        print(f"⚠️ Warning: Could not create backup.", flush=True)
        print(f"Detail: {e}", file=sys.stderr, flush=True)

    # Read current code to include in prompt
    with open(connector_file, 'r') as f:
        original_code = f.read()

    # Session ID is now passed via command-line argument (not loaded from file)
    if session_id:
        print(f"🔗 Attempting to resume generator's session for context continuity")
    else:
        print(f"ℹ️  No previous session provided, starting fresh conversation")

    # Initialize empty conversation history for session-only tool correlation
    conversation_history = []

    if revision_instructions:
        prompt = prompt_template.format(
            project_name=project_name,
            revision_request=revision_instructions,
            project_directory=str(project_dir),
            original_code=original_code
        )
    else:
        prompt = prompt_template.format(
            project_name=project_name,
            error_logs=error_msg,
            project_directory=str(project_dir),
            original_code=original_code
        )

    try:
        # Collect all response content from Claude Agent SDK
        response_parts = []

        # Try to connect with session resumption, fall back to fresh session if it fails
        client = None
        tried_fresh = False

        claude_options, error = get_claude_options_for_fixer(project_dir=project_dir, session_id=session_id)
        if error:
            print(f"❌ {error}")
            cleanup_temp_files(project_dir)
            sys.exit(1)

        client = ClaudeSDKClient(options=claude_options)

        try:
            await client.connect()
        except Exception as connect_error:
            # Session resume failed - try fresh session
            if session_id and not tried_fresh:
                print(f"⚠️  Session expired or invalid, starting fresh conversation")
                tried_fresh = True
                claude_options, error = get_claude_options_for_fixer(project_dir=project_dir, session_id=None)
                if error:
                    print(f"❌ {error}")
                    cleanup_temp_files(project_dir)
                    sys.exit(1)
                client = ClaudeSDKClient(options=claude_options)
                await client.connect()
            else:
                raise connect_error

        try:
            # Send the prompt using query()
            await client.query(prompt)

            # Receive messages
            async for message in client.receive_messages():
                # Collect text content for response parsing
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            response_parts.append(block.text)

                # Display formatted message content
                formatted_message = format_message_for_display(message, conversation_history)
                if formatted_message:
                    sys.stdout.write(formatted_message)
                    if not formatted_message.endswith('\n'):
                        sys.stdout.write('\n')
                    sys.stdout.flush()

                # Add message to history for tool correlation
                conversation_history.append(message)

                # Handle completion
                if isinstance(message, ResultMessage):
                    # ResultMessage indicates completion
                    break  # Exit after receiving result message

        finally:
            # Always disconnect
            await client.disconnect()

        if not revision_instructions:
            full_response = '\n'.join(response_parts)
            if "ERROR_TYPE: USER" in full_response:
                print("\n" + "="*60)
                print("🔍 USER CONFIGURATION ISSUE DETECTED")
                print("="*60)
                print("The AI has determined this is a configuration issue that requires user action.")
                print("💡 Please check: API credentials, network connectivity, permissions, configuration")
                print("📋 Review the detailed guidance above for specific steps to resolve this issue.")
                print("🔄 After making the necessary changes, try running the connector again.")
                print("="*60)
                sys.exit(0)  # Exit successfully for user errors
            elif "ERROR_TYPE: CODE" in full_response:
                print("\n" + "="*60)
                print("🔧 CODE ISSUE DETECTED AND FIXED")
                print("="*60)
                print("The AI has identified and fixed implementation issues in the connector code.")
                print("🧪 Proceeding with state reset and testing to validate the fix...")
                print("="*60)
            else:
                # Neither ERROR_TYPE detected - AI response was incomplete or invalid
                print("\n" + "="*60)
                print("❌ AI FIX INCOMPLETE")
                print("="*60)
                print("The AI was unable to complete the fix (missing error classification).")
                print("Please review the output above and try again.")
                print("="*60)
                cleanup_temp_files(project_dir)
                sys.exit(1)  # Exit with error - don't reset state

        print(f"\n🧪 Resetting state...")
        reset_state(user_workspace, project_name)

        # Request configuration review before testing (same pattern as interactive agent)
        config_file = project_dir / "configuration.json"
        if config_file.exists():
            with open(config_file) as f:
                config = json.load(f)

            if len(config) > 0:
                # Emit CONFIG_REVIEW_REQUIRED for main.py to detect and show popup
                # main.py will merge cached credentials and then clear them
                print(f"CONFIG_REVIEW_REQUIRED:{json.dumps({'configuration': config})}", flush=True)
                print("⏸️  Please review configuration before testing...")
                print("⏸️  Waiting for credentials...\n", flush=True)

                # Read credentials from stdin (sent by main.py after user submits popup)
                credentials_json = sys.stdin.readline().strip()

                if not credentials_json:
                    # User cancelled - skip testing
                    print("⏭️  Configuration review cancelled - skipping testing", flush=True)
                    cleanup_temp_files(project_dir)
                    sys.exit(0)  # Exit without error

                try:
                    credentials_data = json.loads(credentials_json)

                    # Check if empty dict was sent (user cancelled)
                    if not credentials_data or (isinstance(credentials_data, dict) and len(credentials_data) == 0):
                        print("⏭️  Configuration review cancelled - skipping testing", flush=True)
                        cleanup_temp_files(project_dir)
                        sys.exit(0)  # Exit without error

                    sensitive_values = credentials_data.get("credentials", {})

                    # Save credentials to encrypted configuration.json
                    save_credentials_to_config(project_dir, sensitive_values, username)

                    print(f"✅ Configuration received, proceeding with test...\n", flush=True)
                except json.JSONDecodeError as e:
                    print(f"❌ Invalid credentials format.", flush=True)
                    print(f"Detail: {e}", file=sys.stderr, flush=True)
                    cleanup_temp_files(project_dir)
                    sys.exit(1)

        # Automatically run test after successful fix
        print(f"\n🧪 Testing fix...")
        exit_code, test_output = run_tester(project_name, user_workspace)
        if exit_code != 0:
            cleanup_temp_files(project_dir)
            sys.exit(exit_code)

        # Success - cleanup before normal exit
        cleanup_temp_files(project_dir)
    except Exception as e:
        print(f"❌ An unexpected error occurred. Please check the logs.")
        print(f"Detail: {e}", file=sys.stderr, flush=True)
        cleanup_temp_files(project_dir)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
