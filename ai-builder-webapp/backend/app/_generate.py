from typing import Dict, Optional, List, Tuple
from pathlib import Path
import os
import sys
import asyncio
import subprocess
import json
import ast

from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, AssistantMessage, TextBlock, ResultMessage, PermissionResultAllow, PermissionResultDeny
from _run import run_tester
from config import CLAUDE_MODEL, GENERATOR_TOOLS, PERMISSION_MODE, ENV_ANTHROPIC_API_KEY, ENV_ANTHROPIC_API_KEY_FALLBACK
from message_utils import format_message_for_display
from history_utils import get_connectors_dir
from prompt_utils import load_prompt_template


def save_session_id(project_dir: Path, session_id: str):
    """Save session ID to connector directory for later resumption"""
    session_file = project_dir / "session_metadata.json"
    with open(session_file, 'w') as f:
        json.dump({"session_id": session_id}, f, indent=2)


def load_session_id(project_dir: Path) -> Optional[str]:
    """Load session ID from connector directory"""
    session_file = project_dir / "session_metadata.json"
    if session_file.exists():
        try:
            with open(session_file, 'r') as f:
                data = json.load(f)
                return data.get("session_id")
        except (json.JSONDecodeError, FileNotFoundError):
            return None
    return None


def check_python_syntax(project_dir: Path) -> List[Tuple[str, str, int, str]]:
    """
    Check all Python files in project_dir for syntax errors.
    Returns list of (filename, error_type, line_number, error_message) tuples.
    """
    errors = []
    for py_file in project_dir.glob("**/*.py"):
        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                source = f.read()
            ast.parse(source)
        except SyntaxError as e:
            rel_path = py_file.relative_to(project_dir)
            errors.append((
                str(rel_path),
                "SyntaxError",
                e.lineno or 0,
                e.msg or str(e)
            ))
        except Exception as e:
            rel_path = py_file.relative_to(project_dir)
            errors.append((
                str(rel_path),
                type(e).__name__,
                0,
                str(e)
            ))
    return errors


def create_file_access_validator(allowed_dir: Path):
    """Create a permission callback that restricts file access to allowed_dir."""
    async def validate_file_access(tool_name: str, tool_input: dict, context):
        """Validate that file operations only access files within allowed directory."""
        # Only validate file-access tools
        if tool_name not in ["Read", "Write", "Edit", "Glob", "Grep"]:
            return PermissionResultAllow()

        # Extract file path from tool input
        file_path = None
        if tool_name in ["Read", "Write", "Edit"]:
            file_path = tool_input.get("file_path")
        elif tool_name == "Glob":
            # Glob uses 'path' parameter (optional, defaults to cwd)
            file_path = tool_input.get("path")
            if not file_path:
                # If no path specified, Glob uses cwd which is already restricted
                return PermissionResultAllow()
        elif tool_name == "Grep":
            # Grep uses 'path' parameter (optional, defaults to cwd)
            file_path = tool_input.get("path")
            if not file_path:
                # If no path specified, Grep uses cwd which is already restricted
                return PermissionResultAllow()

        if not file_path:
            # No path to validate
            return PermissionResultAllow()

        try:
            # Convert to Path and resolve to absolute path
            requested_path = Path(file_path).resolve()
            allowed_path = allowed_dir.resolve()

            # Check if requested path is within allowed directory
            requested_path.relative_to(allowed_path)
            return PermissionResultAllow()
        except (ValueError, RuntimeError):
            # Path is outside allowed directory
            return PermissionResultDeny(
                message=f"Access denied: {file_path} is outside the project directory",
                interrupt=True
            )

    return validate_file_access


def get_claude_options(api_key: Optional[str] = None, model: Optional[str] = None, cwd: Optional[Path] = None):
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

        # Create file access validator if cwd is provided
        file_validator = create_file_access_validator(cwd) if cwd else None

        options = ClaudeAgentOptions(
            allowed_tools=GENERATOR_TOOLS,
            permission_mode=PERMISSION_MODE,
            model=model,
            cwd=cwd,
            can_use_tool=file_validator
        )
        return options, None
    except Exception as e:
        return None, f"Error creating Claude Agent options: {str(e)}"

async def generate_connector_code(claude_options, project_name: str, description: str, user_code_dir: str, user_workspace: Path) -> tuple[Dict[str, str], Optional[str]]:
    # Validate inputs
    if '..' in project_name or '/' in project_name or len(project_name) > 50:
        raise Exception("Invalid project name")

    # Load templates first
    prompt_template = load_prompt_template("GENERATOR_AGENT")

    # Ensure the project directory exists before running the agent
    code_dir = Path(user_code_dir)
    project_dir = code_dir / project_name

    # Validate project directory is within workspace
    try:
        project_dir.resolve().relative_to(code_dir.resolve())
    except ValueError:
        raise Exception("Project directory outside workspace")

    project_dir.mkdir(parents=True, exist_ok=True)

    # Create virtual environment for dependency isolation using uv (shared cache)
    venv_dir = project_dir / "venv"
    if not venv_dir.exists():
        print("📦 Creating virtual environment for connector...")
        try:
            venv_result = subprocess.run(
                ["uv", "venv", str(venv_dir)],
                capture_output=True,
                text=True,
                timeout=60
            )
            if venv_result.returncode != 0:
                print(f"❌ Failed to create virtual environment: {venv_result.stderr}")
                sys.exit(5)
            print("✅ Virtual environment created")
        except subprocess.TimeoutExpired:
            print("❌ Virtual environment creation timed out")
            sys.exit(5)
        except Exception as e:
            print(f"❌ Error creating virtual environment. Please check the logs.", flush=True)
            print(f"Detail: {e}", file=sys.stderr, flush=True)
            sys.exit(5)

    # Verify the target directory exists
    if not code_dir.exists():
        raise Exception(f"User code directory does not exist: {code_dir}")

    # Format the prompt template with variables
    prompt = prompt_template.format(
        project_name=project_name,
        description=description,
        project_directory=str(project_dir)
    )

    # Initialize conversation history for tool correlation only
    conversation_history = []
    response_parts = []
    captured_session_id = None

    try:
        # Use ClaudeSDKClient for native session management
        client = ClaudeSDKClient(options=claude_options)

        # Connect (without prompt - we'll send it via query())
        await client.connect()

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
                    # Capture session ID for continuation by fixer agent
                    captured_session_id = message.session_id
                    break  # Exit after receiving result message

        finally:
            # Always disconnect
            await client.disconnect()

        full_response = '\n'.join(response_parts)
        return _parse_response(full_response), captured_session_id

    except Exception as e:
        raise Exception(f"Error generating code: {str(e)}")

def remove_markdown(code):
    # remove lines that begin with ```
    return "\n".join(line for line in code.splitlines() if not line.strip().startswith("```"))


def _parse_response(response: str) -> Dict[str, str]:
    """Parse the Claude response into separate files"""
    files = {}

    sections = {
        'connector.py': '=== CONNECTOR.PY ===',
        'configuration.json': '=== CONFIGURATION.JSON ===',
        'requirements.txt': '=== REQUIREMENTS.TXT ===',
        'README.md': '=== README.MD ==='
    }

    for filename, marker in sections.items():
        try:
            start = response.find(marker)
            if start == -1:
                continue

            start += len(marker)

            # Find the next section or end of response
            next_markers = [m for m in sections.values() if m != marker]
            end = len(response)
            for next_marker in next_markers:
                next_pos = response.find(next_marker, start)
                if next_pos != -1 and next_pos < end:
                    end = next_pos

            content = response[start:end].strip()
            content = remove_markdown(content)
            files[filename] = content

        except Exception as e:
            files[filename] = f"Error parsing {filename}: {str(e)}"

    return files


def save_connector_files(project_name: str, files: Dict[str, str], user_code_dir: str) -> tuple[bool, Optional[Exception]]:
    """Save the generated files to the user's workspace directory"""
    try:
        # Validate project name to prevent path traversal
        if '..' in project_name or '/' in project_name or '\\' in project_name:
            raise Exception(f"Invalid project name: {project_name}. Cannot contain path separators or '..'")

        # Create project directory
        code_dir = Path(user_code_dir)
        project_dir = code_dir / project_name

        # Ensure project directory is within user workspace
        try:
            project_dir.resolve().relative_to(code_dir.resolve())
        except ValueError:
            raise Exception(f"Project directory outside workspace: {project_dir}")

        project_dir.mkdir(parents=True, exist_ok=True)

        # Save each file with validation
        saved_files = []
        for filename, content in files.items():
            # Validate filename to prevent path traversal
            if '..' in filename or '/' in filename or '\\' in filename:
                raise Exception(f"Invalid filename: {filename}. Cannot contain path separators or '..'")

            file_path = project_dir / filename

            # Ensure file is within project directory
            try:
                file_path.resolve().relative_to(project_dir.resolve())
            except ValueError:
                raise Exception(f"File path outside project directory: {file_path}")

            with open(file_path, 'w') as f:
                f.write(content)
            saved_files.append(str(file_path))

        return True, None

    except Exception as e:
        return False, e


def cleanup_temp_files(project_dir: Path):
    """Clean up any temporary files (named pipes)."""
    for temp_file in [".config_pipe"]:
        temp_path = project_dir / temp_file
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass


async def main():
    project_name = sys.argv[1]
    description = sys.argv[2]
    api_key = sys.argv[3]
    user_workspace = Path(sys.argv[4])
    user_code_dir = get_connectors_dir(user_workspace)

    code_dir = Path(user_code_dir)
    project_dir = code_dir / project_name
    connector_file = project_dir / "connector.py"

    print(f'🚀 Deploying connector generator agent...', flush=True)
    # Use environment variable for API key instead of command line argument
    claude_options, error = get_claude_options(cwd=project_dir)

    # Check if there was an error getting Claude options
    if error:
        print(f"❌ {error}")
        sys.exit(5)

    files, session_id = await generate_connector_code(claude_options, project_name, description, str(user_code_dir), user_workspace)

    # Output session ID for main.py to capture (instead of saving to file)
    if session_id:
        print(f"SESSION_ID:{session_id}")

    # Save files
    save_result, error = save_connector_files(project_name, files, str(user_code_dir))
    if not save_result:
        print(f'\n❌ Unable to save project files: {error}')
        sys.exit(5)

    # Check for Python syntax errors and ask AI to fix them
    print("🔍 Checking Python syntax...")
    syntax_errors = check_python_syntax(project_dir)
    max_fix_attempts = 2
    fix_attempt = 0

    while syntax_errors and fix_attempt < max_fix_attempts:
        fix_attempt += 1
        print(f"⚠️ Found {len(syntax_errors)} syntax error(s), asking AI to fix (attempt {fix_attempt}/{max_fix_attempts})...")

        # Format errors for the AI
        error_details = []
        for filename, error_type, line_no, message in syntax_errors:
            error_details.append(f"- {filename} line {line_no}: {error_type}: {message}")

        fix_prompt = f"""The generated Python code has syntax errors that need to be fixed:

{chr(10).join(error_details)}

Please read the affected file(s), fix the syntax errors, and save the corrected code. Common issues include:
- Markdown formatting (like ---) accidentally included in Python code
- Missing colons, parentheses, or quotes
- Invalid indentation
- Incomplete statements

Fix all syntax errors while preserving the intended functionality."""

        # Create new options for fix attempt (reuse session if available)
        fix_options, fix_error = get_claude_options(session_id=session_id, cwd=user_workspace)
        if fix_error:
            print(f"⚠️ Could not create fix session: {fix_error}")
            break

        # Ask AI to fix the errors
        try:
            fix_files, new_session_id = await generate_connector_code(fix_options, project_name, fix_prompt, str(user_code_dir), user_workspace)
            if new_session_id:
                session_id = new_session_id

            # Save fixed files
            if fix_files:
                save_result, error = save_connector_files(project_name, fix_files, str(user_code_dir))
                if not save_result:
                    print(f"⚠️ Could not save fixed files: {error}")

            # Check again
            syntax_errors = check_python_syntax(project_dir)
            if not syntax_errors:
                print("✅ Syntax errors fixed successfully!")
        except Exception as e:
            print(f"⚠️ Error during fix attempt: {e}")
            break

    if syntax_errors:
        print(f"⚠️ {len(syntax_errors)} syntax error(s) remain - you may need to fix manually")
        for filename, error_type, line_no, message in syntax_errors:
            print(f"   - {filename} line {line_no}: {message}")
    else:
        print("✅ Python syntax check passed")

    # Generate requirements.txt using pipreqs for accurate dependencies
    print("📦 Generating requirements.txt using pipreqs...")
    requirements_path = project_dir / "requirements.txt"

    # Get pipreqs from the same venv as the running Python interpreter
    pipreqs_path = Path(sys.executable).parent / "pipreqs"

    # Use subprocess.run to capture output properly
    result = subprocess.run(
        [str(pipreqs_path), str(project_dir), "--force", "--ignore", ".git,venv", "--savepath", str(requirements_path)],
        capture_output=True,
        text=True,
        check=False
    )

    # Parse and display output with appropriate prefixes
    output = result.stdout + result.stderr
    for line in output.strip().split('\n'):
        if line.strip():
            if line.startswith('INFO:'):
                print(f"{line}")
            elif line.startswith('WARNING:'):
                print(f"⚠️  {line}")
            elif 'Successfully saved' in line:
                print(f"✅ {line}")
            elif line.startswith('Please, verify'):
                print(f"💡 {line}")
            else:
                print(f"   {line}")

    if result.returncode != 0:
        print(f"⚠️ pipreqs failed (possibly due to syntax errors in generated code) - creating minimal requirements.txt")
        # Create a minimal requirements.txt so generation can continue
        with open(requirements_path, 'w') as f:
            f.write("# Auto-generated minimal requirements\n")
        print("✅ Created minimal requirements.txt - you may need to add dependencies manually")
    else:
        # Remove dependencies that are not needed
        with open(requirements_path, 'r') as f:
            lines = f.readlines()
        with open(requirements_path, 'w') as f:
            for line in lines:
                if line.lower().startswith("fivetran_connector_sdk") or line.lower().startswith("requests"):
                    continue
                f.write(line)
        print("✅ Requirements.txt generated successfully")

    print("Installing requirements ...")
    requirements_path = code_dir / project_name / "requirements.txt"
    if not requirements_path.exists():
        print(f"❌ Requirements file not found at: {requirements_path}")
        print("❌ This indicates the connector generation failed or files weren't saved properly.")
        sys.exit(5)

    # Use uv pip to install dependencies (uses shared cache for faster installs)
    import select
    import time

    venv_dir = project_dir / "venv"
    venv_python = venv_dir / "bin" / "python"
    if not venv_python.exists():
        print(f"❌ Virtual environment Python not found at: {venv_python}")
        sys.exit(5)

    try:
        process = subprocess.Popen([
            "uv", "pip", "install", "-r", str(requirements_path), "--python", str(venv_python)
        ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True)

        # Stream output in real-time
        start_time = time.time()
        while process.poll() is None:
            if time.time() - start_time > 60:  # 60 second timeout
                print("❌ uv pip install timed out after 60 seconds. This may indicate:")
                print("  - Network connectivity issues")
                print("  - Large package downloads")
                print("  - System resource constraints")
                process.kill()
                process.wait(timeout=5)
                sys.exit(1)

            # Use select to check for available output (non-blocking)
            if select.select([process.stdout], [], [], 0.1)[0]:
                line = process.stdout.readline()
                if line:
                    print(line.rstrip(), flush=True)

        # Read any remaining output
        for line in iter(process.stdout.readline, ''):
            print(line.rstrip(), flush=True)

        process.wait()

        if process.returncode != 0:
            print(f"❌ Installing requirements failed with exit code: {process.returncode}")
            sys.exit(5)

    except Exception as e:
        print(f"❌ Error installing dependencies. Please check the logs.", flush=True)
        print(f"Detail: {e}", file=sys.stderr, flush=True)
        sys.exit(5)

    # Install fivetran_connector_sdk separately (not in requirements.txt for customer deployment)
    print("📦 Installing fivetran_connector_sdk for local testing...")
    try:
        sdk_process = subprocess.run(
            ["uv", "pip", "install", "fivetran_connector_sdk", "--python", str(venv_python)],
            capture_output=True,
            text=True,
            timeout=120
        )

        if sdk_process.returncode != 0:
            print(f"❌ Failed to install fivetran_connector_sdk: {sdk_process.stderr}")
            sys.exit(5)

        print("✅ fivetran_connector_sdk installed")
    except subprocess.TimeoutExpired:
        print("❌ SDK installation timed out")
        sys.exit(5)
    except Exception as e:
        print(f"❌ Error installing SDK. Please check the logs.", flush=True)
        print(f"Detail: {e}", file=sys.stderr, flush=True)
        sys.exit(5)

    # Verify that connector.py was actually created
    if not connector_file.exists():
        # Clean up incomplete project
        if project_dir.exists():
            import shutil
            shutil.rmtree(project_dir)
            print(f"🧹 Cleaned up incomplete project folder\n")
        sys.exit(5)
    else:
        print(f"✅ Connector created successfully\n")

    # Generation complete - skip automatic testing
    # User can manually click "Run" to test the connector with credentials
    print("📋 Generation complete. Click 'Run' to test your connector.")
    cleanup_temp_files(project_dir)
    sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
