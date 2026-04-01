# Plan: AI Provider Agnostic Architecture

## Current State Analysis

The app currently uses Claude Agent SDK directly in 4 agent files:
- `_generate.py` - Connector code generation
- `_fix_revise.py` - Auto-fix and revision
- `_interact.py` - Interactive chat with code editing
- `_validate.py` - Description validation

### Claude-specific dependencies used:
- `ClaudeSDKClient` - Client for async message streaming
- `ClaudeAgentOptions` - Configuration (model, tools, permissions, session resume)
- Message types: `AssistantMessage`, `TextBlock`, `ToolUseBlock`, `ResultMessage`
- Permission types: `PermissionResultAllow`, `PermissionResultDeny`
- Session continuity via `resume=session_id`

### 5 specialized agents with different tool permissions:
| Agent     | Tools                                     |
|-----------|-------------------------------------------|
| Generator | Task, Read, Write, Edit, WebFetch         |
| Fixer     | Task, Read, Edit, WebFetch                |
| Reviser   | Task, Read, Edit, WebFetch                |
| Interact  | Task, Read, Edit, WebFetch, Grep, Glob    |
| Validator | Task, Read, WebFetch                      |

---

## Recommended Architecture

### 1. Create Abstract AI Provider Interface

Create `backend/app/ai_providers/base.py`:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Optional, List, Callable, Any, Dict
from pathlib import Path
from enum import Enum

class MessageType(Enum):
    TEXT = "text"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    COMPLETION = "completion"

@dataclass
class ToolConfig:
    name: str
    description: str
    input_schema: Dict[str, Any]

@dataclass
class AIMessage:
    type: MessageType
    content: str = ""
    tool_name: Optional[str] = None
    tool_input: Optional[Dict] = None
    tool_use_id: Optional[str] = None
    session_id: Optional[str] = None

@dataclass
class PermissionResult:
    allowed: bool
    message: str = ""

@dataclass
class AIClientConfig:
    model: str
    allowed_tools: List[str]
    cwd: Optional[Path] = None
    resume_session: Optional[str] = None
    permission_callback: Optional[Callable] = None

class AIProvider(ABC):
    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the AI provider."""
        pass

    @abstractmethod
    async def query(self, prompt: str) -> None:
        """Send a prompt to the AI."""
        pass

    @abstractmethod
    async def receive_messages(self) -> AsyncIterator[AIMessage]:
        """Stream messages from the AI."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close the connection."""
        pass
```

### 2. Implement Claude Provider

Create `backend/app/ai_providers/claude_provider.py`:

```python
from .base import AIProvider, AIMessage, AIClientConfig, MessageType
from claude_agent_sdk import (
    ClaudeSDKClient, ClaudeAgentOptions,
    AssistantMessage, TextBlock, ToolUseBlock, ResultMessage,
    PermissionResultAllow, PermissionResultDeny
)

class ClaudeProvider(AIProvider):
    def __init__(self, config: AIClientConfig, api_key: str):
        self.config = config
        self.api_key = api_key
        self.client = None

    async def connect(self):
        options = ClaudeAgentOptions(
            allowed_tools=self.config.allowed_tools,
            permission_mode="acceptEdits",
            model=self.config.model,
            resume=self.config.resume_session,
            cwd=self.config.cwd,
            can_use_tool=self._wrap_permission_callback()
        )
        self.client = ClaudeSDKClient(options=options)
        await self.client.connect()

    async def query(self, prompt: str):
        await self.client.query(prompt)

    async def receive_messages(self):
        async for message in self.client.receive_messages():
            yield self._convert_message(message)

    async def disconnect(self):
        await self.client.disconnect()

    def _convert_message(self, msg) -> AIMessage:
        # Convert Claude-specific types to generic AIMessage
        if isinstance(msg, ResultMessage):
            return AIMessage(
                type=MessageType.COMPLETION,
                session_id=msg.session_id
            )
        elif isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    return AIMessage(type=MessageType.TEXT, content=block.text)
                elif isinstance(block, ToolUseBlock):
                    return AIMessage(
                        type=MessageType.TOOL_USE,
                        tool_name=block.name,
                        tool_input=block.input,
                        tool_use_id=block.id
                    )
        return AIMessage(type=MessageType.TEXT, content="")
```

### 3. Create Provider Factory

Create `backend/app/ai_providers/factory.py`:

```python
from typing import Optional
from pathlib import Path
from .base import AIProvider, AIClientConfig
from .claude_provider import ClaudeProvider

def create_ai_provider(
    provider_type: str,
    api_key: str,
    model: str,
    allowed_tools: list,
    cwd: Path = None,
    resume_session: str = None,
    permission_callback = None
) -> AIProvider:

    config = AIClientConfig(
        model=model,
        allowed_tools=allowed_tools,
        cwd=cwd,
        resume_session=resume_session,
        permission_callback=permission_callback
    )

    if provider_type == "claude":
        return ClaudeProvider(config, api_key)
    elif provider_type == "openai":
        # Future: return OpenAIProvider(config, api_key)
        raise NotImplementedError("OpenAI provider not yet implemented")
    else:
        raise ValueError(f"Unknown provider type: {provider_type}")
```

### 4. Update Agent Files

Modify each agent file to use the abstraction layer. Example for `_generate.py`:

```python
from ai_providers.factory import create_ai_provider
from ai_providers.base import AIMessage, MessageType

async def generate_connector_code(provider_type: str, api_key: str, ...):
    provider = create_ai_provider(
        provider_type=provider_type,
        api_key=api_key,
        model=get_model_for_provider(provider_type),
        allowed_tools=["Task", "Read", "Write", "Edit", "WebFetch"],
        cwd=project_dir,
        permission_callback=create_file_access_validator(project_dir)
    )

    await provider.connect()
    try:
        await provider.query(prompt)
        async for message in provider.receive_messages():
            if message.type == MessageType.TEXT:
                response_parts.append(message.content)
            elif message.type == MessageType.COMPLETION:
                captured_session_id = message.session_id
                break
    finally:
        await provider.disconnect()
```

### 5. Add Provider Configuration

Update `main.py` to accept provider selection:

```python
class GenerateConnectorRequest(BaseModel):
    project_name: str
    description: str
    ai_provider: str = "claude"  # Default to Claude
    # api_key: Optional[str] = None  # User's own API key (future)
```

---

## Files to Create/Modify

### New Files:
- `backend/app/ai_providers/__init__.py`
- `backend/app/ai_providers/base.py` - Abstract interface
- `backend/app/ai_providers/claude_provider.py` - Claude implementation
- `backend/app/ai_providers/factory.py` - Provider factory

### Files to Modify:
- `backend/app/_generate.py` - Use provider abstraction
- `backend/app/_fix_revise.py` - Use provider abstraction
- `backend/app/_interact.py` - Use provider abstraction
- `backend/app/_validate.py` - Use provider abstraction
- `backend/app/main.py` - Add provider selection to API

---

## Key Considerations

### Session Continuity
The `resume=session_id` feature is Claude-specific. For other providers:
- Store conversation history in the abstraction layer
- Pass history with each request for stateless providers
- Abstract session management in `AIProvider` base class

### Tool Permissions
Claude Agent SDK has a unique tool permission model. For other providers:
- Implement tool calling via function_call API (OpenAI)
- Abstract permission validation at the factory level
- Fall back to history-based context for providers without native tools

### Streaming
All providers must implement `receive_messages()` as async generator:
- Claude: Native async iteration
- OpenAI: Streaming completion API
- Others: Polling or SSE depending on provider

---

## Verification Plan

1. **Unit Tests**: Create tests for each provider in `backend/tests/test_ai_providers.py`
2. **Integration Tests**: Test full generation flow with mock providers
3. **Manual Testing**:
   - Generate a connector using Claude provider
   - Verify session continuity (Generator → Fixer → Interact)
   - Verify file access permissions work correctly
4. **Frontend**: No changes needed - API remains the same

---

## Future Enhancements

1. **OpenAI Provider**: Implement using GPT-4 with function calling
2. **User API Keys**: Allow users to provide their own API keys
3. **Model Selection**: Let users choose specific models per provider
4. **Fallback**: Auto-fallback to different provider on failures
