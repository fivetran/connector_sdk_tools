"""
Fivetran Connector Interactive Agent

Unified agent that can both analyze (answer questions) and revise (make changes)
to connector code in a natural conversational flow with full session context.
"""

import sys
import asyncio
import shutil
import json
import stat
from datetime import datetime
from pathlib import Path

from prompt_utils import load_prompt_template
from config import CLAUDE_MODEL, INTERACTIVE_TOOLS, PERMISSION_MODE, ENV_ANTHROPIC_API_KEY, ENV_ANTHROPIC_API_KEY_FALLBACK
import os
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, AssistantMessage, TextBlock, ResultMessage, ToolUseBlock, PermissionResultAllow, PermissionResultDeny
from message_utils import format_message_for_display
from history_utils import get_connectors_dir
from _run import run_tester


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


def get_claude_options_for_interact(session_id=None, project_dir=None):
    """Get Claude options for interactive agent with both analysis and revision capabilities."""
    api_key = os.getenv(ENV_ANTHROPIC_API_KEY) or os.getenv(ENV_ANTHROPIC_API_KEY_FALLBACK)

    if not api_key:
        return None, f"{ENV_ANTHROPIC_API_KEY} (or {ENV_ANTHROPIC_API_KEY_FALLBACK}) environment variable not found"

    model = CLAUDE_MODEL

    try:
        os.environ['ANTHROPIC_API_KEY'] = api_key

        # Create file access validator if project_dir is provided
        file_validator = create_file_access_validator(project_dir) if project_dir else None

        options = ClaudeAgentOptions(
            allowed_tools=INTERACTIVE_TOOLS,
            permission_mode=PERMISSION_MODE,
            model=model,
            resume=session_id,  # Resume generator's session for full context
            cwd=project_dir,
            can_use_tool=file_validator
        )
        return options, None
    except Exception as e:
        return None, f"Error creating Claude Agent options: {str(e)}"


def reset_state(user_workspace: Path, project_name: str) -> int:
    """Reset connector state by deleting the files directory."""
    files_dir = get_connectors_dir(user_workspace) / project_name / "files"
    if files_dir.exists():
        try:
            shutil.rmtree(files_dir)
            return 0
        except Exception as e:
            print(f"⚠️ Warning: Could not reset state.", flush=True)
            print(f"Detail: {e}", file=sys.stderr, flush=True)
            return -1
    else:
        return -2


def create_backup_if_needed(connector_file: Path, project_dir: Path) -> bool:
    """Create a timestamped backup of connector.py if it hasn't been created yet.

    Returns:
        bool: True if backup was created, False if it already existed or failed
    """
    try:
        # Create timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Create archive folder if it doesn't exist
        archive_dir = project_dir / "archive"
        archive_dir.mkdir(exist_ok=True)

        # Create backup
        backup_file = archive_dir / f"connector.py.{timestamp}"
        shutil.copy2(connector_file, backup_file)
        print(f"📋 Created backup: archive/{backup_file.name}")
        return True
    except Exception as e:
        print(f"⚠️ Warning: Could not create backup.", flush=True)
        print(f"Detail: {e}", file=sys.stderr, flush=True)
        return False


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
    # Parse arguments
    if len(sys.argv) < 4:
        print("Usage: python _interact.py <project_name> <user_message> <user_workspace> [session_id]")
        sys.exit(1)

    project_name = sys.argv[1]
    user_message = sys.argv[2]
    user_workspace = Path(sys.argv[3])

    # Session ID can come from 4th argument (in-memory) or file (first interaction after generator)
    session_id = sys.argv[4] if len(sys.argv) > 4 else None

    # Extract username from workspace path (e.g., "../workspaces/john_doe" -> "john_doe")
    username = user_workspace.name

    user_code_dir = get_connectors_dir(user_workspace)
    project_dir = user_code_dir / project_name

    print(f"\n💬 Interactive agent ready for: {project_name}")

    # Verify connector exists
    connector_file = project_dir / "connector.py"
    if not connector_file.exists():
        print(f"❌ connector.py not found in {project_dir}")
        cleanup_temp_files(project_dir)
        sys.exit(1)

    # Backup will be created lazily if/when Edit tool is used
    # Load prompt template
    prompt_template = load_prompt_template("INTERACT_AGENT")

    # Read current code to provide context
    with open(connector_file, 'r') as f:
        original_code = f.read()

    # Session ID is passed via command-line argument from main.py (stored in session.json)
    if session_id:
        print(f"🔗 Attempting to continue conversation with previous context")
    else:
        print(f"ℹ️  No previous session provided, starting fresh conversation")

    # Format prompt with context
    prompt = prompt_template.format(
        project_name=project_name,
        user_message=user_message,
        project_directory=str(project_dir),
        original_code=original_code
    )

    # Initialize conversation history for tool correlation
    conversation_history = []
    new_session_id = None
    response_parts = []  # Collect response text for error classification
    code_was_modified = False  # Track if Edit tool was used
    backup_created = False  # Track if backup was created

    # Try to connect with session resumption, fall back to fresh session if it fails
    client = None
    tried_fresh = False

    try:
        # First attempt: try with session_id if provided
        claude_options, error = get_claude_options_for_interact(session_id=session_id, project_dir=project_dir)
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
                claude_options, error = get_claude_options_for_interact(session_id=None, project_dir=project_dir)
                if error:
                    print(f"❌ {error}")
                    cleanup_temp_files(project_dir)
                    sys.exit(1)
                client = ClaudeSDKClient(options=claude_options)
                await client.connect()
            else:
                raise connect_error

        try:
            # Send the user's message
            await client.query(prompt)

            # Receive and stream messages
            async for message in client.receive_messages():
                # Collect text content for error classification
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            response_parts.append(block.text)
                        # Detect Edit tool usage
                        elif isinstance(block, ToolUseBlock) and block.name == "Edit":
                            # Create backup before first edit if not already created
                            if not backup_created:
                                backup_created = create_backup_if_needed(connector_file, project_dir)
                            code_was_modified = True

                # Format and display other messages (tool use, results, etc.)
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
                    # Capture session ID to continue conversation in next interaction
                    new_session_id = message.session_id
                    break

        finally:
            # Always disconnect
            await client.disconnect()

        # Check for error classification in response
        full_response = '\n'.join(response_parts)
        if "ERROR_TYPE: USER" in full_response:
            print("\n" + "="*60)
            print("🔍 CONFIGURATION ISSUE DETECTED")
            print("="*60)
            print("The agent has identified this as a configuration or environmental issue.")
            print("💡 Please review the guidance above for specific steps to resolve.")
            print("📋 This is not a code issue - check your configuration, credentials, or environment.")
            print("="*60)
        elif "ERROR_TYPE: CODE" in full_response:
            print("\n" + "="*60)
            print("🔧 CODE ISSUE IDENTIFIED")
            print("="*60)
            print("The agent has identified and potentially fixed implementation issues.")
            print("💡 Review the changes above and test the connector when ready.")
            print("🧪 Proceeding with state reset and testing to validate the fix...")
            print("="*60)

        # Auto-reset state and test if code was modified
        if code_was_modified:
            print(f"\n🧪 Resetting state...")
            reset_state(user_workspace, project_name)

            # Always request configuration review before testing (regardless of cached credentials)
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
                    print("🔐 Reading credentials from stdin...", flush=True)
                    credentials_json = sys.stdin.readline().strip()

                    if not credentials_json:
                        # User cancelled - skip testing
                        print("⏭️  Configuration review cancelled - skipping testing", flush=True)
                        code_was_modified = False  # Prevent testing
                    else:
                        try:
                            credentials_data = json.loads(credentials_json)

                            # Check if empty dict was sent (user cancelled)
                            if not credentials_data or (isinstance(credentials_data, dict) and len(credentials_data) == 0):
                                print("⏭️  Configuration review cancelled - skipping testing", flush=True)
                                code_was_modified = False  # Prevent testing
                            else:
                                sensitive_values = credentials_data.get("credentials", {})

                                # Save credentials to encrypted configuration.json
                                save_credentials_to_config(project_dir, sensitive_values, username)

                                print(f"✅ Configuration received, proceeding with test...\n", flush=True)
                        except json.JSONDecodeError as e:
                            print(f"❌ Invalid credentials format.", flush=True)
                            print(f"Detail: {e}", file=sys.stderr, flush=True)

        # Auto-reset state and test if code was modified
        if code_was_modified:
            print(f"\n🧪 Auto-testing changes...")
            exit_code, test_output = run_tester(project_name, user_workspace)

            if exit_code != 0:
                print("\n⚠️ Tests failed - AI is investigating the issue...")

                # Loop back to AI to investigate the test failure
                try:
                    # Reconnect using session ID to continue conversation
                    claude_options, error = get_claude_options_for_interact(session_id=new_session_id, project_dir=project_dir)
                    if error:
                        print(f"⚠️ Could not reconnect to AI: {error}")
                    else:
                        client = ClaudeSDKClient(options=claude_options)
                        await client.connect()

                        try:
                            # Send the test failure to AI for investigation
                            investigation_prompt = f"""The connector test just failed. Please analyze the error output and fix the issues in connector.py.

TEST OUTPUT:
{test_output}

Please:
1. Identify what went wrong
2. Fix the connector.py code to resolve the error
3. The fixes should address the root cause shown in the test output"""

                            await client.query(investigation_prompt)

                            # Receive and stream AI's investigation response
                            async for message in client.receive_messages():
                                if isinstance(message, AssistantMessage):
                                    for block in message.content:
                                        if isinstance(block, ToolUseBlock) and block.name == "Edit":
                                            code_was_modified = True

                                formatted_message = format_message_for_display(message, conversation_history)
                                if formatted_message:
                                    sys.stdout.write(formatted_message)
                                    if not formatted_message.endswith('\n'):
                                        sys.stdout.write('\n')
                                    sys.stdout.flush()

                                conversation_history.append(message)

                                if isinstance(message, ResultMessage):
                                    new_session_id = message.session_id
                                    break
                        finally:
                            await client.disconnect()

                        # If AI made more changes, run tests again
                        if code_was_modified:
                            print(f"\n🧪 Re-testing after AI fixes...")
                            reset_state(user_workspace, project_name)
                            exit_code, test_output = run_tester(project_name, user_workspace)
                            if exit_code == 0:
                                print("✅ Tests passed after AI fix!")
                            else:
                                print("⚠️ Tests still failing - you may need to continue the conversation")

                except Exception as e:
                    print(f"⚠️ Could not auto-investigate the failure.", flush=True)
                    print(f"Detail: {e}", file=sys.stderr, flush=True)
                    print("💡 You can continue the conversation to fix issues or click 'Debug' to see full output")
            else:
                print("✅ Tests passed!")

        # Output new session ID for main.py to capture and store in-memory
        if new_session_id:
            print(f"SESSION_ID:{new_session_id}")

        print("\n✅ Interaction complete")

        # Clean up credentials file before exit
        cleanup_temp_files(project_dir)
        sys.exit(0)

    except Exception as e:
        print(f"❌ An unexpected error occurred. Please check the logs.")
        print(f"Detail: {e}", file=sys.stderr, flush=True)
        # Clean up credentials file before exit
        cleanup_temp_files(project_dir)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
