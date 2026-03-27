# Centralized configuration for AI agents
# Update settings here to change them everywhere

from pathlib import Path

# =============================================================================
# AI Model Configuration
# =============================================================================
CLAUDE_MODEL = "claude-sonnet-4-6"

# =============================================================================
# Agent Tool Configurations
# =============================================================================
VALIDATION_TOOLS = ["Read", "WebFetch"]
GENERATOR_TOOLS = ["Write", "WebFetch"]
FIXER_TOOLS = ["Read", "Edit", "WebFetch", "Grep", "Glob"]
INTERACTIVE_TOOLS = ["Read", "Edit", "WebFetch", "Grep", "Glob"]

# Permission mode for all agents
PERMISSION_MODE = "acceptEdits"

# =============================================================================
# Workspace Configuration
# =============================================================================
BASE_DIR = Path(__file__).resolve().parent.parent / "workspaces"

# =============================================================================
# Environment Variable Names
# =============================================================================
ENV_ANTHROPIC_API_KEY = "CSDKAI_ANTHROPIC_API_KEY"
ENV_ANTHROPIC_API_KEY_FALLBACK = "ANTHROPIC_API_KEY"
ENV_GOOGLE_CLIENT_ID = "CSDKAI_GOOGLE_CLIENT_ID"
ENV_ALLOWED_DOMAINS = "CSDKAI_ALLOWED_DOMAINS"
ENV_ALLOWED_ORIGINS = "CSDKAI_ALLOWED_ORIGINS"
ENV_MASTER_SECRET = "CSDKAI_MASTER_SECRET"
