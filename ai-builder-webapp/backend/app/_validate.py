"""
Fivetran Connector Validation Agent

This script conducts an interactive conversation with users to validate and enhance
their connector descriptions, ensuring all required information is gathered before
generation begins.
"""

import sys
import asyncio
import os
import re
from pathlib import Path
from typing import Dict, Any, List

from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, AssistantMessage, TextBlock, UserMessage, ResultMessage, PermissionResultAllow, PermissionResultDeny
from prompt_utils import load_prompt_template
from config import CLAUDE_MODEL, VALIDATION_TOOLS, PERMISSION_MODE, ENV_ANTHROPIC_API_KEY, ENV_ANTHROPIC_API_KEY_FALLBACK


def create_file_access_validator(allowed_dir: Path):
    """Create a permission callback that restricts file access to allowed_dir."""
    async def validate_file_access(tool_name: str, tool_input: dict, context):
        """Validate that file operations only access files within allowed directory."""
        # Only validate file-access tools (validation agent only has Read, not Write/Edit)
        if tool_name not in ["Read"]:
            return PermissionResultAllow()

        # Extract file path from tool input
        file_path = tool_input.get("file_path")

        if not file_path:
            return PermissionResultAllow()

        try:
            requested_path = Path(file_path).resolve()
            allowed_path = allowed_dir.resolve()
            requested_path.relative_to(allowed_path)
            return PermissionResultAllow()
        except (ValueError, RuntimeError):
            return PermissionResultDeny(
                message=f"Access denied: {file_path} is outside the workspace directory",
                interrupt=True
            )

    return validate_file_access


def get_validation_claude_options(session_id: str = None, cwd: Path = None):
    """Get Claude options specifically configured for validation.

    Args:
        session_id: Optional Claude Code session ID to resume a previous conversation
        cwd: Current working directory for the validation agent
    """
    # Get API key from environment variable
    api_key = os.getenv(ENV_ANTHROPIC_API_KEY) or os.getenv(ENV_ANTHROPIC_API_KEY_FALLBACK)

    if not api_key:
        return None, f"{ENV_ANTHROPIC_API_KEY} (or {ENV_ANTHROPIC_API_KEY_FALLBACK}) environment variable not found"

    model = CLAUDE_MODEL

    try:
        # Set the API key as environment variable for claude-agent-sdk
        os.environ['ANTHROPIC_API_KEY'] = api_key

        # Create file access validator if cwd is provided
        file_validator = create_file_access_validator(cwd) if cwd else None

        # Use ClaudeAgentOptions from claude-agent-sdk
        options = ClaudeAgentOptions(
            allowed_tools=VALIDATION_TOOLS,
            permission_mode=PERMISSION_MODE,
            model=model,
            resume=session_id,  # Resume previous session if provided
            cwd=cwd,
            can_use_tool=file_validator
        )
        return options, None
    except Exception as e:
        return None, f"Error creating Claude Agent options: {str(e)}"


class ValidationState:
    """Manages the state of the validation conversation."""
    
    def __init__(self):
        self.questions_asked = 0
        self.critical_gaps_filled = []
        self.validation_complete = False
        self.enhanced_description = ""
        self.conversation_summary = {}
        
    def add_gap_filled(self, gap: str):
        """Record a critical gap that was filled."""
        self.critical_gaps_filled.append(gap)
        
    def increment_questions(self):
        """Increment question counter."""
        self.questions_asked += 1
        
    def set_complete(self, enhanced_description: str):
        """Mark validation as complete with final description."""
        self.validation_complete = True
        self.enhanced_description = enhanced_description
        self.conversation_summary = {
            "questions_asked": self.questions_asked,
            "critical_gaps_filled": self.critical_gaps_filled,
            "ready_for_generation": True
        }


def extract_validation_status(text: str) -> Dict[str, Any]:
    """Extract validation status and enhanced description from agent response."""
    result = {
        "is_complete": False,
        "enhanced_description": "",
        "needs_more_info": True,
        "next_question": "",
        "conversation_summary": {}
    }
    
    # Check for completion marker
    if "VALIDATION COMPLETE" in text:
        result["is_complete"] = True
        result["needs_more_info"] = False
        
        # Extract the enhanced description section
        enhanced_match = re.search(r"ENHANCED DESCRIPTION:\s*(.*?)(?=VALIDATION COMPLETE|$)", text, re.DOTALL | re.IGNORECASE)
        if enhanced_match:
            result["enhanced_description"] = enhanced_match.group(1).strip()
        else:
            # Fallback to full response if enhanced description not found
            result["enhanced_description"] = text.strip()
    else:
        # Extract next question or response
        result["next_question"] = text.strip()
    
    return result


async def validate_description(
    claude_options: ClaudeAgentOptions,
    project_name: str,
    initial_description: str,
    user_workspace: Path,
    conversation_messages: List = None
) -> Dict[str, Any]:
    """
    Conduct validation conversation with the user.

    Args:
        claude_options: Claude Agent SDK configuration
        project_name: Name of the project
        initial_description: User's initial description
        user_workspace: User's workspace path
        conversation_messages: Existing conversation messages for continuation

    Returns:
        Dict containing validation results and enhanced description
    """

    # Load validation prompt template
    prompt_template = load_prompt_template("VALIDATION_AGENT")
    if not prompt_template or prompt_template.startswith("Prompt template"):
        raise Exception("VALIDATION_AGENT prompt template not found")

    # Initialize validation state
    validation_state = ValidationState()

    # Get username for persistent history
    username = user_workspace.name

    # Prepare prompt - check if we're resuming a session or have conversation history
    is_resuming_session = claude_options.resume is not None
    original_session_id = claude_options.resume
    has_conversation_history = conversation_messages and len(conversation_messages) > 0

    if is_resuming_session:
        # Continuing conversation - just send the user's response without template
        context_prompt = initial_description
    elif has_conversation_history:
        # We have prior conversation - include only the most recent AI feedback for context
        # Format: original prompt template + last AI feedback + new user response

        # Get the original description from first user message in history
        original_description = conversation_messages[0].get('content', '') if conversation_messages else initial_description
        initial_prompt = prompt_template.replace('{{CONNECTOR_DESCRIPTION}}', original_description)

        # Find the most recent assistant message
        last_assistant_msg = None
        for msg in reversed(conversation_messages):
            if msg.get('role') == 'assistant':
                last_assistant_msg = msg.get('content', '')
                break

        # Build context with just the last AI feedback
        context_lines = []
        if last_assistant_msg:
            context_lines.append(f"\n\n--- YOUR PREVIOUS FEEDBACK ---\n{last_assistant_msg}\n--- END PREVIOUS FEEDBACK ---\n")

        # Add the new user submission
        context_lines.append(f"\n[USER'S RESPONSE]:\n{initial_description}\n")
        context_lines.append("\nPlease evaluate this response in the context of your previous feedback. If the user has addressed your concerns satisfactorily, you may mark validation as complete.")

        context_prompt = initial_prompt + ''.join(context_lines)
    else:
        # For initial validation, wrap in full prompt template
        # Replace placeholder with actual description
        initial_prompt = prompt_template.replace('{{CONNECTOR_DESCRIPTION}}', initial_description)
        context_prompt = initial_prompt

    # Collect response parts
    response_parts = []
    captured_session_id = None

    try:
        # Try to connect with session resumption, fall back to fresh session if it fails
        client = None
        tried_fresh = False
        current_options = claude_options

        client = ClaudeSDKClient(options=current_options)

        try:
            await client.connect()
        except Exception as connect_error:
            # Session resume failed - try fresh session
            if is_resuming_session and not tried_fresh:
                print(f"⚠️  Session expired or invalid, starting fresh validation")
                tried_fresh = True
                # Get fresh options without session_id
                current_options, error = get_validation_claude_options(session_id=None, cwd=user_workspace)
                if error:
                    raise Exception(error)
                # Use full prompt template since we're starting fresh
                context_prompt = prompt_template.replace('{{CONNECTOR_DESCRIPTION}}', initial_description)
                client = ClaudeSDKClient(options=current_options)
                await client.connect()
            else:
                raise connect_error

        try:
            # Send the prompt using query()
            await client.query(context_prompt)

            # Receive messages
            async for message in client.receive_messages():
                # Collect text content for response parsing
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            response_parts.append(block.text)
                            # Display only AssistantMessage text content to user
                            sys.stdout.write(block.text)
                            sys.stdout.write('\n')
                            sys.stdout.flush()

                # Handle completion
                elif isinstance(message, ResultMessage):
                    # ResultMessage indicates completion
                    # Capture session ID for continuation
                    captured_session_id = message.session_id
                    # Could log: message.duration, message.cost, message.usage
                    break  # Exit after receiving result message

                # Skip SystemMessage and other internal messages - don't display to user
        finally:
            # Always disconnect
            await client.disconnect()

        # Combine response parts
        full_response = '\n'.join(response_parts)

        # Extract validation status
        validation_result = extract_validation_status(full_response)

        # Return validation results with session ID
        return {
            "success": True,
            "validation_complete": validation_result["is_complete"],
            "enhanced_description": validation_result["enhanced_description"],
            "needs_more_info": validation_result["needs_more_info"],
            "agent_response": full_response,
            "session_id": captured_session_id,  # Return session ID for continuation
            "conversation_history": []  # Not needed with ClaudeSDKClient
        }

    except Exception as e:
        print(f"Detail: {e}", file=sys.stderr, flush=True)
        return {
            "success": False,
            "error": "An unexpected error occurred during validation.",
            "validation_complete": False,
            "enhanced_description": "",
            "needs_more_info": True,
            "agent_response": "An unexpected error occurred during validation. Please try again."
        }


async def continue_validation_conversation(
    claude_options: ClaudeAgentOptions,
    project_name: str,
    user_response: str,
    user_workspace: Path
) -> Dict[str, Any]:
    """
    Continue an existing validation conversation with a user response.

    Args:
        claude_options: Claude Agent SDK configuration
        project_name: Name of the project
        user_response: User's response to the agent's question
        user_workspace: User's workspace path

    Returns:
        Dict containing validation results
    """

    # Get username for persistent history
    username = user_workspace.name

    # For now, treat as new conversation with user response as input
    # Future enhancement: implement session ID persistence for true continuation
    return await validate_description(
        claude_options=claude_options,
        project_name=project_name,
        initial_description=user_response,
        user_workspace=user_workspace,
        conversation_messages=None  # Start fresh for now
    )


async def main():
    """Main function for validation script."""
    if len(sys.argv) < 4:
        print("Usage: python _validate.py <project_name> <initial_description> <user_workspace> [user_response]")
        sys.exit(1)
    
    project_name = sys.argv[1]
    initial_description = sys.argv[2]
    user_workspace = Path(sys.argv[3])
    user_response = sys.argv[4] if len(sys.argv) > 4 else None
    
    print(f'🔍 Deploying validation agent for project: {project_name}', flush=True)

    # Get Claude options for validation
    claude_options, error = get_validation_claude_options(cwd=user_workspace)
    if error:
        print(f"❌ {error}")
        sys.exit(1)
    
    try:
        if user_response:
            # Continue existing conversation
            result = await continue_validation_conversation(
                claude_options=claude_options,
                project_name=project_name,
                user_response=user_response,
                user_workspace=user_workspace
            )
        else:
            # Start new validation conversation
            result = await validate_description(
                claude_options=claude_options,
                project_name=project_name,
                initial_description=initial_description,
                user_workspace=user_workspace
            )
        
        # Output results - always include agent response to show assumptions
        agent_response = result.get("agent_response", "")
        
        if result.get("validation_complete"):
            # For successful validation, include the full agent response that contains assumptions
            if agent_response and ("ASSUMPTIONS" in agent_response or "VALIDATION COMPLETE" in agent_response):
                print(agent_response)
            else:
                print("✅ Validation complete! Enhanced description ready for generation.")
            sys.exit(0)
        else:
            print("\nPlease update your description above to include the following information:")
            # Extract and display just the agent response
            if agent_response:
                print(agent_response)
            sys.exit(2)  # Exit code 2 indicates more input needed
            
    except Exception as e:
        print(f"❌ Validation error. Please check the logs.")
        print(f"Detail: {e}", file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
