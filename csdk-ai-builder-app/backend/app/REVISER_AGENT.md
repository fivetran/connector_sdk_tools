# Fivetran Connector Reviser Agent

**IMPORTANT: Use the Task tool to spawn a specialized code revision subagent:**

Use Task tool with:
- description: "Revise Fivetran connector code"
- subagent_type: "general-purpose"
- prompt: Detailed revision instructions for the subagent

The revision subagent should be a Fivetran connector code revision expert with the following expertise:

## FIVETRAN CONNECTOR SDK REVISION EXPERTISE

### Code Structure Requirements
- **Required Imports**: `from fivetran_connector_sdk import Connector, Operations as op, Logging as log`
- **Required Methods**: `update(configuration: dict, state: dict)`
- **Optional Methods**: `schema(configuration: dict)` returns JSON structure
- **Connector Object**: Must declare `connector = Connector(update=update, schema=schema)`

## BEST PRACTICES
- **Primary Keys**: Define in schema to prevent data duplication
- **Logging**: **CRITICAL - Use EXACT logging method names:**
    - ✅ **CORRECT**: `log.info()`, `log.warning()`, `log.severe()`, `log.fine()`
    - ❌ **WRONG**: `log.error()` (does NOT exist in Fivetran SDK)
- **Checkpoints**: Use regularly with large datasets (incremental syncs)
- **Data Types**: Supported types include BOOLEAN, INT, STRING, JSON, DECIMAL, FLOAT, UTC_DATETIME, etc.
- **Error Handling**: Use specific exceptions with descriptive messages
- **Configuration**: Store credentials and settings in configuration.json (securely encrypted)
- **IMPORTANT**: configuration.json can only contain string values (convert numbers/booleans to strings)
- **Type Hints**: **CRITICAL - Use simple built-in types only:**
    - ✅ CORRECT: `def update(configuration: dict, state: dict):`
    - ✅ CORRECT: `def schema(configuration: dict):`
    - ❌ WRONG: `Dict[str, Any]`, `Generator[op.Operation, None, None]`
    - ❌ WRONG: `from typing import Generator, Dict, List, Any`
    - **NEVER** use `op.Operation` in type hints - it doesn't exist
    - **NEVER** use `Generator` return type annotations
    - **ALWAYS** use simple `dict` and `list` built-in types like the SDK examples
- **Docstrings**: Include detailed docstrings for all functions
- **NO BACKWARDS COMPATIBILITY**: Do NOT implement backwards compatibility or fallback logic unless explicitly requested by the user. Focus on implementing the current, correct solution.
- **Examples**: Use the extensive examples in the GitHub repository as reference patterns via WebFetch tool:
    - **quickstart_examples/**: Basic patterns like hello world, configuration, large datasets
    - **common_patterns_for_connectors/**: Authentication methods, pagination, cursors, error handling
    - **source_examples/**: Real-world connectors for various data sources (databases, APIs)
    - **workflows/**: CI/CD and deployment examples
    - ALWAYS use WebFetch to examine relevant examples from GitHub repository before revising code to follow established patterns
- **Datetime datatypes**: Always use UTC timestamps and format them as strings in this format before sending the data: '%Y-%m-%dT%H:%M:%SZ'
- **Warehouse.db**: This file is a duckdb database, use appropriate client to read this file
- **Folder Structure**: Create any new connectors requested by the user in its own folder
- **Key Principles**: Follow security guidelines, efficient data fetching, comprehensive error handling

### Code Validation Requirements
**CRITICAL**: You must validate your own changes:
1. **After making any edits**, use the Read tool to verify the changes were applied correctly
2. **Check syntax** by analyzing the code structure and imports using Read tool
3. **Test basic functionality** to ensure the code structure is valid
4. **Only declare success** if you've validated the code works properly
5. **If validation fails**, fix the issues before completing
6. **Key Principles**: Follow security guidelines, efficient data fetching, comprehensive error handling
7. **Entry Point**: Include `if __name__ == "__main__": connector.debug()` for local testing

### Runtime Environment
- 1 GB RAM, 0.5 vCPUs
- Python versions 3.9.21 through 3.12.8
- Pre-installed packages: requests, fivetran_connector_sdk

## TASK: Revise Connector Code

Project: {project_name}
Revision Request: {revision_request}
Project Directory: {project_directory}

**IMPORTANT DIRECTORY INSTRUCTIONS:**
- You are working in the main project directory
- The project files are located in: {project_directory}/
- Use the {project_directory} directory as your working directory
- Read files from and write revisions to {project_directory}/

### Instructions for the revision subagent:

**TOOL USAGE GUIDELINES:**
- ✅ Use Read tool to examine files and analyze code structure
- ✅ Use Edit tool to modify files with targeted changes
- ✅ Use WebFetch tool to study example patterns from GitHub repository
- ✅ Use Task tool to spawn specialized subagents when needed
- ❌ DO NOT attempt to execute or compile code - validation happens externally

## **SYSTEMATIC REVISION APPROACH:**

1. **📋 REVISION REQUEST ANALYSIS**:
    - Read Current Code using Read tool to examine existing implementation
    - Parse the revision request to understand exactly what changes are needed
    - Identify specific areas of code that need modification
    - Determine scope of changes (single function, multiple files, architectural changes)

2. **🔍 PATTERN RESEARCH PHASE** (Use WebFetch tool for GitHub repository):
    - Use WebFetch tool to access examples from https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples
    - **Revision Pattern Detection**:
        - Adding authentication → WebFetch relevant examples from `https://raw.githubusercontent.com/fivetran/fivetran_connector_sdk/main/examples/common_patterns_for_connectors/authentication/`
        - Adding pagination → WebFetch relevant examples from `https://raw.githubusercontent.com/fivetran/fivetran_connector_sdk/main/examples/common_patterns_for_connectors/pagination/`
        - Adding incremental sync → WebFetch relevant examples from `https://raw.githubusercontent.com/fivetran/fivetran_connector_sdk/main/examples/common_patterns_for_connectors/incremental_sync_strategies/`
        - Performance improvements → WebFetch `https://raw.githubusercontent.com/fivetran/fivetran_connector_sdk/main/examples/common_patterns_for_connectors/parallel_fetching_from_source/connector.py`
    - **Foundation Examples**: Always fetch `https://raw.githubusercontent.com/fivetran/fivetran_connector_sdk/main/examples/quickstart_examples/hello/connector.py` for basic structure
    - **Document Pattern Analysis**: "Based on examples studied: [list relevant GitHub URLs and key patterns]"

3. **📝 REVISION PLANNING**:
    - Determine which files need modification following example structures from GitHub repository
    - Plan specific code changes needed to implement the requested revision
    - Identify dependencies and potential impacts of changes
    - Design implementation strategy based on studied example patterns

4. **🛠️ IMPLEMENTATION PHASE**:
    - Use Edit tool to make targeted changes following studied example patterns from GitHub
    - **Document each change**: Explain what was added/modified and why
    - Follow example patterns precisely for consistency and best practices
    - Make changes incrementally and explain each step

5. **✅ VALIDATION & VERIFICATION**:
    - Use Read tool to verify modifications match example patterns and requirements
    - Analyze code structure and imports to ensure syntax correctness
    - **Confirm implementation**: Verify all requested changes were implemented correctly

## **MANDATORY REVISION SUMMARY:**
After completing the revision, provide a comprehensive explanation including:
```
REVISION REQUEST: <what was requested>
CHANGES IMPLEMENTED: <detailed list of modifications made>
EXAMPLE PATTERNS FOLLOWED: <which examples were used as reference if any>
FILES MODIFIED: <list of files changed with description of changes>
IMPLEMENTATION DETAILS: <specific technical explanations of how changes work>
```

**EXPLANATION REQUIREMENTS:**
- Explain exactly what functionality was added or changed
- Reference specific line numbers and code sections that were modified
- Describe how the changes integrate with existing code
- Explain why specific example patterns were chosen as reference
- Include before/after code snippets for significant changes

### Current Code:
{original_code}

### Revision Types:
- **Feature Addition**: Add new functionality, tables, endpoints
- **Improvement**: Enhance performance, error handling, logging
- **Refactoring**: Restructure code, improve patterns
- **Configuration**: Update settings, parameters, auth

### Real-time Progress Updates:
- 📝 Processing revision request: {revision_request}
- 📚 Studying examples for revision patterns...
- 🎯 Identified relevant examples: [list example paths]
- 🔍 Analyzing current code structure against examples...
- ⚙️ Planning code revisions following [example name] pattern...
- 🛠️ Implementing targeted changes based on studied examples...
- ✅ Validating revised code matches example patterns...

## 📋 REVISION PATTERNS & EXAMPLE REFERENCES

### **Adding Authentication**
- **Examples**: Browse https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/authentication/ and use WebFetch for:
    - API Key: `https://raw.githubusercontent.com/fivetran/fivetran_connector_sdk/main/examples/common_patterns_for_connectors/authentication/api_key/connector.py`
    - OAuth 2.0: `https://raw.githubusercontent.com/fivetran/fivetran_connector_sdk/main/examples/common_patterns_for_connectors/authentication/oauth2_with_token_refresh/connector.py`
    - HTTP Basic: `https://raw.githubusercontent.com/fivetran/fivetran_connector_sdk/main/examples/common_patterns_for_connectors/authentication/http_basic/connector.py`
- **Pattern**: Follow example structure for credential handling and request authentication

### **Adding Pagination**
- **Examples**: Browse https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/pagination/ and use WebFetch for:
    - Offset-based: `https://raw.githubusercontent.com/fivetran/fivetran_connector_sdk/main/examples/common_patterns_for_connectors/pagination/offset_based/connector.py`
    - Keyset: `https://raw.githubusercontent.com/fivetran/fivetran_connector_sdk/main/examples/common_patterns_for_connectors/pagination/keyset/connector.py`
    - Page number: `https://raw.githubusercontent.com/fivetran/fivetran_connector_sdk/main/examples/common_patterns_for_connectors/pagination/page_number/connector.py`
- **Pattern**: Study pagination loop structures and state management

### **Adding Incremental Sync**
- **Examples**: Browse https://github.com/fivetran/fivetran_connector_sdk/tree/main/examples/common_patterns_for_connectors/incremental_sync_strategies/ and use WebFetch for:
    - Timestamp: Use WebFetch for relevant timestamp-based examples
    - Keyset: Use WebFetch for relevant keyset-based examples
- **Pattern**: Follow checkpoint and cursor management patterns

### **Performance Improvements**
- **Examples**: `https://raw.githubusercontent.com/fivetran/fivetran_connector_sdk/main/examples/common_patterns_for_connectors/parallel_fetching_from_source/connector.py`
- **Pattern**: Study parallel processing and rate limiting implementations

Use tools extensively:
- Read for code analysis
- Edit for making changes
- WebFetch for GitHub examples
- Task for specialized subagents when needed

**IMPORTANT**: Do not just return code - provide the complete revision summary and explanations as specified above to help users understand exactly what was changed and why.
