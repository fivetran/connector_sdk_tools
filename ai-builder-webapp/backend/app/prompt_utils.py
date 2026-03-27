"""Utility functions for loading prompt templates."""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_prompt_template(prompt_name: str) -> str:
    """Load a prompt template from the app directory.

    Args:
        prompt_name: Name of the template (without .md extension)

    Returns:
        Template content if successful, error message starting with "Prompt template" if not
    """
    try:
        # Get the directory where this script is located (app directory)
        script_dir = Path(__file__).parent
        prompt_path = script_dir / f"{prompt_name}.md"
        logger.info(f"load_prompt_template: Looking for {prompt_path}, exists={prompt_path.exists()}")
        with open(prompt_path, 'r') as f:
            content = f.read()
            logger.info(f"load_prompt_template: Loaded {len(content)} chars from {prompt_name}.md")
            return content
    except FileNotFoundError as e:
        logger.error(f"load_prompt_template: FileNotFoundError - {e}")
        return f"Prompt template {prompt_name} not found"
    except Exception as e:
        logger.error(f"load_prompt_template: Unexpected error - {type(e).__name__}: {e}")
        return f"Prompt template {prompt_name} not found (error: {e})"
