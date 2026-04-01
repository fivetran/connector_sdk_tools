# Storage Structure Refactor Plan

## Current State

Currently, both deployable files and internal state are mixed in `connectors/{name}/`:

```
workspaces/{username}/
├── connectors/{name}/          # Mixed: deployable + state
│   ├── connector.py            # Deployable
│   ├── configuration.json      # Deployable
│   ├── requirements.txt        # Deployable
│   ├── files/warehouse.db      # Deployable (sync output)
│   ├── venv/                   # Runtime (excluded from download)
│   ├── chat_history.json       # State
│   ├── .generation_complete    # State
│   ├── .session_id             # State
│   ├── .config_metadata.json   # State
│   └── .configuration.runtime.json  # State (temporary)
│
└── projects/
    └── {name}.json             # Metadata only
```

## Proposed Structure

Separate deployable files from internal state:

```
workspaces/{username}/
├── connectors/{name}/          # Deployable files ONLY
│   ├── connector.py
│   ├── configuration.json
│   ├── requirements.txt
│   ├── files/warehouse.db
│   └── venv/                   # Runtime (still excluded from download)
│
└── projects/{name}/            # Metadata + state
    ├── metadata.json           # Project info (currently {name}.json in projects/)
    ├── chat_history.json       # AI builder conversation
    ├── .generation_complete    # Generation status marker
    ├── .session_id             # Claude SDK session for resumption
    └── .config_metadata.json   # Tracks sensitive config fields
```

## Benefits

1. **Clean downloads/deployments**: `connectors/{name}/` contains only what's needed to run
2. **Clear separation**: State/metadata vs deployable code
3. **Easier cleanup**: Can delete `connectors/{name}/` without losing chat history
4. **Simpler exclusions**: No need for complex file filtering in download endpoint

## Migration Steps

### Phase 1: Move `.generation_complete` (COMPLETED 2026-02-05)
- [x] Store `.generation_complete` in `projects/{name}/` instead of `connectors/{name}/`
- [x] Update `/connector-generation-status` endpoint (with backward compatibility)
- [x] Update generation completion markers in `main.py`
- [x] Update marker deletion on regeneration (checks both locations)

### Phase 2: Move chat_history.json (COMPLETED 2026-02-05)
- [x] Update `save_connector_chat_message()` to use projects path
- [x] Update `get_connector_chat_history()` endpoint (with backward compatibility)
- [x] Update `save_project_data()` to create chat_history.json in projects dir
- [x] Migration script for existing data (manual migration supported via backward compatibility)

### Phase 3: Move .session_id
- [ ] Update `save_session_id()` in `history_utils.py`
- [ ] Update `load_session_id()` in `history_utils.py`
- [ ] Update `clear_session_id()` in `history_utils.py`

### Phase 4: Move .config_metadata.json
- [ ] Update config save endpoint
- [ ] Update all places that read sensitivity metadata
- [ ] Migration script for existing data

### Phase 5: ~~Move temporary credential files~~ (REMOVED 2026-02-05)
- [x] **No longer needed**: Config is now passed to SDK via named pipe (`.config_pipe`)
- [x] Decryption happens in memory, no temp files written to disk

### Phase 6: Convert projects/{name}.json to projects/{name}/metadata.json
- [ ] Update `_get_user_connectors_internal()` to read from subdirectory
- [ ] Update project creation to use subdirectory structure
- [ ] Migration script for existing `.json` files

## Files to Modify

### main.py
- `save_connector_chat_message()` - chat history path
- `get_connector_chat_history()` - chat history path
- `get_connector_generation_status()` - marker path
- Generation endpoints - marker creation
- Config endpoints - metadata path
- Debug/interact endpoints - credentials path
- `_get_user_connectors_internal()` - metadata path

### history_utils.py
- `save_session_id()` - session file path
- `load_session_id()` - session file path
- `clear_session_id()` - session file path

### Frontend (App.tsx)
- No changes needed (uses API endpoints)

## Backward Compatibility

For migration, check both old and new locations:
```python
def get_project_state_dir(user_workspace: dict, project_name: str) -> Path:
    """Get the project state directory, creating if needed."""
    projects_dir = Path(user_workspace["projects"])
    project_state_dir = projects_dir / project_name
    project_state_dir.mkdir(parents=True, exist_ok=True)
    return project_state_dir

def get_state_file(user_workspace: dict, project_name: str, filename: str) -> Path:
    """Get path to a state file, checking new location first, then old."""
    # New location: projects/{name}/{filename}
    new_path = Path(user_workspace["projects"]) / project_name / filename
    if new_path.exists():
        return new_path

    # Old location: connectors/{name}/{filename}
    old_path = Path(user_workspace["connectors"]) / project_name / filename
    if old_path.exists():
        return old_path

    # Default to new location for new files
    return new_path
```

## Testing

After each phase:
1. Create new project - verify files in correct location
2. Load existing project - verify backward compatibility
3. Download connector - verify no state files included
4. Delete connector files - verify state preserved
