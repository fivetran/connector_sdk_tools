"""Utility functions for handling Claude Code SDK messages."""
import json
import re

def extract_filename_from_tool_content(content):
    """Extract filename from Read/Write tool content."""
    if isinstance(content, list) and len(content) > 0:
        if isinstance(content[0], dict) and 'text' in content[0]:
            content_str = content[0]['text']
        else:
            content_str = str(content[0])
    else:
        content_str = str(content)
    
    # Look for common file path patterns
    import re
    import os
    
    # Try to find absolute paths
    path_patterns = [
        r'/[^/\s]+(?:/[^/\s]*)*\.py',  # /path/to/file.py
        r'/[^/\s]+(?:/[^/\s]*)*\.[a-zA-Z0-9]+',  # /path/to/file.ext
        r'file_path.*?([\'"])([^\'"]+\.[a-zA-Z]+)\1',  # file_path: "filename"
    ]
    
    for pattern in path_patterns:
        matches = re.findall(pattern, content_str)
        if matches:
            if isinstance(matches[0], tuple):  # For patterns with groups
                filepath = matches[0][-1]
            else:
                filepath = matches[0]
            # Return just the filename, not full path
            return os.path.basename(filepath)
    
    return "file"

def format_read_tool_excerpt(content):
    """Format Read tool results to show filename with file info and excerpt."""
    filename = extract_filename_from_tool_content(content)
    
    # Try to extract additional information from the content
    content_str = str(content)
    
    # Count lines in the file content
    if isinstance(content, list) and len(content) > 0:
        if isinstance(content[0], dict) and 'text' in content[0]:
            file_content = content[0]['text']
        else:
            file_content = str(content[0])
    else:
        file_content = content_str
    
    # Count lines (look for line number patterns like "123→")
    import re
    line_matches = re.findall(r'^\s*(\d+)→', file_content, re.MULTILINE)
    line_count = len(line_matches) if line_matches else len(file_content.split('\n'))
    
    # Determine file type and icon
    file_ext = filename.split('.')[-1].lower() if '.' in filename else ''
    file_icons = {
        'py': '🐍', 'js': '📜', 'ts': '📘', 'tsx': '⚛️', 'jsx': '⚛️',
        'json': '📋', 'md': '📝', 'txt': '📄', 'yaml': '📊', 'yml': '📊',
        'sql': '🗄️', 'csv': '📊', 'html': '🌐', 'css': '🎨', 'scss': '🎨',
        'java': '☕', 'cpp': '⚙️', 'c': '⚙️', 'go': '🐹', 'rs': '🦀',
        'php': '🐘', 'rb': '💎', 'sh': '🔧', 'dockerfile': '🐳'
    }
    
    file_icon = file_icons.get(file_ext, '📄')
    
    # Extract a small excerpt (first few non-empty lines)
    lines = file_content.split('\n')
    excerpt_lines = []
    
    for line in lines[:5]:  # First 5 lines
        # Remove line number prefix if present
        clean_line = re.sub(r'^\s*\d+→\s*', '', line).strip()
        if clean_line and not clean_line.startswith('<system-reminder>'):
            excerpt_lines.append(clean_line)
            if len(excerpt_lines) >= 2:  # Show max 2 meaningful lines
                break
    
    # Format the excerpt
    if excerpt_lines:
        excerpt = " | ".join(excerpt_lines)
        if len(excerpt) > 80:
            excerpt = excerpt[:77] + "..."
    else:
        excerpt = "Empty file"
    
    # Calculate file size estimate (rough)
    size_chars = len(file_content)
    if size_chars > 1024:
        size_info = f"{size_chars // 1024}KB"
    else:
        size_info = f"{size_chars}B"
    
    return f"{file_icon} **{filename}** ({line_count} lines, {size_info})\n   `{excerpt}`"

def format_search_results(content, tool_name):
    """Format Grep/Glob search results with counts and highlighting."""
    content_str = str(content)
    
    if not content_str or content_str.strip() == "":
        return f"🔍 **{tool_name}**: No results found"
    
    # Handle different content formats
    if isinstance(content, list) and len(content) > 0:
        if isinstance(content[0], dict) and 'text' in content[0]:
            results_text = content[0]['text']
        else:
            results_text = str(content[0])
    else:
        results_text = content_str
    
    lines = results_text.strip().split('\n')
    
    # Filter out system reminders and empty lines
    clean_lines = []
    for line in lines:
        clean_line = line.strip()
        if clean_line and not clean_line.startswith('<system-reminder>'):
            clean_lines.append(clean_line)
    
    if not clean_lines:
        return f"🔍 **{tool_name}**: No results found"
    
    result_count = len(clean_lines)
    
    # For Grep results, try to extract file paths and match context
    if 'Grep' in tool_name:
        files_found = set()
        matches_with_context = []
        
        for line in clean_lines[:10]:  # Show max 10 results
            # Look for file paths (common patterns)
            if ':' in line and ('/' in line or '\\' in line):
                parts = line.split(':', 1)
                if len(parts) == 2:
                    file_path = parts[0]
                    match_content = parts[1].strip()
                    
                    # Extract just filename
                    import os
                    filename = os.path.basename(file_path)
                    files_found.add(filename)
                    
                    # Truncate long matches
                    if len(match_content) > 60:
                        match_content = match_content[:57] + "..."
                    
                    matches_with_context.append(f"   📄 {filename}: `{match_content}`")
                else:
                    # Just a file path
                    import os
                    filename = os.path.basename(line)
                    files_found.add(filename)
                    matches_with_context.append(f"   📄 {filename}")
            else:
                # Direct content match
                if len(line) > 60:
                    line = line[:57] + "..."
                matches_with_context.append(f"   💬 `{line}`")
        
        # Create summary
        file_count = len(files_found)
        summary = f"🔍 **{tool_name}**: {result_count} matches"
        if file_count > 0:
            summary += f" in {file_count} file{'s' if file_count != 1 else ''}"
        
        if matches_with_context:
            return summary + "\n" + '\n'.join(matches_with_context)
        else:
            return summary
    
    # For Glob results, show file listing with counts
    elif 'Glob' in tool_name:
        files_by_type = {}
        directories = []
        
        for line in clean_lines:
            import os
            if os.path.isdir(line) or line.endswith('/'):
                directories.append(line)
            else:
                # Get file extension
                ext = os.path.splitext(line)[1].lower()
                if ext:
                    ext = ext[1:]  # Remove the dot
                    files_by_type[ext] = files_by_type.get(ext, 0) + 1
                else:
                    files_by_type['no-ext'] = files_by_type.get('no-ext', 0) + 1
        
        summary = f"🔍 **{tool_name}**: {result_count} items found"
        
        details = []
        if directories:
            details.append(f"   📁 {len(directories)} directories")
        
        if files_by_type:
            file_total = sum(files_by_type.values())
            details.append(f"   📄 {file_total} files")
            
            # Show file type breakdown for variety
            if len(files_by_type) > 1:
                type_summary = []
                for ext, count in sorted(files_by_type.items(), key=lambda x: -x[1])[:3]:
                    type_summary.append(f"{ext}: {count}")
                details.append(f"      ({', '.join(type_summary)})")
        
        if details:
            return summary + "\n" + '\n'.join(details)
        else:
            return summary
    
    # Generic search results
    else:
        summary = f"🔍 **{tool_name}**: {result_count} results"
        if result_count <= 5:
            # Show all results if few
            result_lines = []
            for line in clean_lines:
                if len(line) > 60:
                    line = line[:57] + "..."
                result_lines.append(f"   • {line}")
            return summary + "\n" + '\n'.join(result_lines)
        else:
            # Just show count for many results
            return summary

def format_error_message(content):
    """Format error messages with better structure and actionable information."""
    content_str = str(content)
    
    # Check if this looks like an error with ERROR_TYPE classification
    if 'ERROR_TYPE:' in content_str:
        lines = content_str.split('\n')
        error_type = None
        error_analysis = []
        suggestions = []
        
        for line in lines:
            line = line.strip()
            if line.startswith('ERROR_TYPE:'):
                error_type = line.replace('ERROR_TYPE:', '').strip()
            elif line.startswith('ANALYSIS:') or line.startswith('Error:') or line.startswith('❌'):
                error_analysis.append(line)
            elif line.startswith('SUGGESTION:') or line.startswith('💡') or line.startswith('FIX:'):
                suggestions.append(line)
        
        if error_type:
            # Format based on error type
            if error_type == 'USER':
                icon = '⚠️'
                title = '**Configuration Issue**'
                color_indicator = '🟡'
            else:  # CODE
                icon = '🔧'
                title = '**Implementation Issue**'
                color_indicator = '🔴'
            
            formatted_parts = [f"{icon} {title} {color_indicator}"]
            
            if error_analysis:
                formatted_parts.append("\n**Analysis:**")
                for analysis in error_analysis[:3]:  # Max 3 analysis lines
                    formatted_parts.append(f"   • {analysis}")
            
            if suggestions:
                formatted_parts.append("\n**Next Steps:**")
                for suggestion in suggestions[:3]:  # Max 3 suggestions
                    formatted_parts.append(f"   ▶️ {suggestion}")
            
            return '\n'.join(formatted_parts)
    
    # Check for common error patterns and enhance them
    if any(error_word in content_str.lower() for error_word in ['error:', 'failed:', 'exception:', 'traceback:']):
        lines = content_str.split('\n')
        
        # Find the main error message
        main_error = None
        for line in lines:
            if any(pattern in line.lower() for pattern in ['error:', 'failed:', 'exception:']):
                main_error = line.strip()
                break
        
        if main_error:
            # Truncate very long error messages
            if len(main_error) > 100:
                main_error = main_error[:97] + "..."
            
            return f"❌ **Error Detected**\n   💬 `{main_error}`\n   📋 Check logs for detailed information"
    
    # Return original content if no special error formatting needed
    return content_str

def format_todowrite_content(content):
    """Format TodoWrite tool results to show todo list without confirmation message."""
    content_str = str(content)
    
    # Always skip confirmation messages - we only want todo list data
    if "Todos have been modified successfully" in content_str:
        return "⏳"  # Activity indicator instead of silence
    
    # Look for structured todo data in JSON format within the content
    try:
        import json
        import re
        
        # Look for JSON-like structures with todo data
        json_match = re.search(r'\[.*\]', content_str, re.DOTALL)
        if json_match:
            try:
                todos = json.loads(json_match.group())
                if isinstance(todos, list) and len(todos) > 0:
                    todo_lines = []
                    completed_count = 0
                    in_progress_count = 0
                    pending_count = 0
                    
                    for i, todo in enumerate(todos, 1):
                        if isinstance(todo, dict):
                            task_content = todo.get('content', 'Unknown task')
                            status = todo.get('status', 'unknown')
                            active_form = todo.get('activeForm', task_content)
                            
                            # Count status types
                            if status == 'completed':
                                completed_count += 1
                            elif status == 'in_progress':
                                in_progress_count += 1
                            elif status == 'pending':
                                pending_count += 1
                            
                            # Use activeForm for in_progress tasks, content for others
                            display_text = active_form if status == 'in_progress' else task_content
                            
                            # Format with status emoji and better visual hierarchy
                            status_emoji = {'pending': '⏳', 'in_progress': '🔄', 'completed': '✅'}.get(status, '❓')
                            
                            # Truncate long task descriptions for better readability
                            if len(display_text) > 60:
                                display_text = display_text[:57] + "..."
                            
                            todo_lines.append(f"{status_emoji} {display_text}")
                    
                    if todo_lines:
                        # Calculate progress percentage
                        total_tasks = len(todos)
                        progress_pct = int((completed_count / total_tasks) * 100) if total_tasks > 0 else 0
                        
                        # Create progress bar
                        bar_length = 10
                        filled_length = int(bar_length * completed_count // total_tasks) if total_tasks > 0 else 0
                        progress_bar = "█" * filled_length + "░" * (bar_length - filled_length)
                        
                        # Create header with progress summary
                        header = f"📋 **Task Progress** ({progress_pct}%) {progress_bar}\n"
                        header += f"   ✅ {completed_count} completed  🔄 {in_progress_count} active  ⏳ {pending_count} pending"
                        
                        return header + "\n\n" + '\n'.join(todo_lines)
            except json.JSONDecodeError:
                pass
        
        # Fallback: look for todo-like patterns in plain text
        lines = content_str.split('\n')
        todo_lines = []
        
        for line in lines:
            if any(status in line.lower() for status in ['pending', 'in_progress', 'completed']):
                clean_line = line.strip()
                if clean_line and 'Todos have been modified' not in clean_line:
                    todo_lines.append(clean_line)
        
        if todo_lines:
            return f"📋 **Current Tasks:**\n" + '\n'.join(todo_lines[:5])
            
    except:
        pass
    
    return "⏳"  # Activity indicator for filtered content

def filter_file_content_from_response(text_content):
    """Remove large file content dumps from AI responses while preserving commentary.

    Only filter actual file content sections (=== FILENAME ===), not regular AI text.
    """
    import re

    # Early return if content is short - likely just commentary
    if len(text_content) < 500:
        return text_content

    # Track files mentioned for summary
    files_mentioned = set()

    # Find file section headers and extract filenames
    file_sections = re.finditer(r'^=+\s*([A-Z_\.]+)\s*=+$', text_content, re.MULTILINE | re.IGNORECASE)
    for match in file_sections:
        files_mentioned.add(match.group(1).lower())

    # Only filter if we detect file section markers (=== FILENAME ===)
    if not files_mentioned:
        # No file sections detected - return as-is (preserve AI commentary)
        return text_content

    # Remove file sections (=== FILENAME === until next === or ## section header or absolute end)
    text_content = re.sub(r'^=+\s*[A-Z_\.]+\s*=+$.*?(?=^===|^##|\Z)', '', text_content, flags=re.MULTILINE | re.DOTALL | re.IGNORECASE)

    # Clean up any standalone file section headers that might remain
    text_content = re.sub(r'^=+\s*[A-Z_\.]+\s*=+$', '', text_content, flags=re.MULTILINE | re.IGNORECASE)

    # Clean up multiple consecutive empty lines
    lines = text_content.split('\n')
    final_lines = []
    prev_empty = False

    for line in lines:
        is_empty = not line.strip()
        if is_empty and prev_empty:
            continue  # Skip consecutive empty lines
        final_lines.append(line)
        prev_empty = is_empty

    # Generate file summary if files were mentioned
    result = '\n'.join(final_lines).strip()
    
    if files_mentioned:
        file_list = sorted(list(files_mentioned))
        if len(file_list) == 1:
            file_summary = f"\n\n📄 **Generated:** {file_list[0]}"
        elif len(file_list) <= 3:
            file_summary = f"\n\n📄 **Generated:** {', '.join(file_list)}"
        else:
            file_summary = f"\n\n📄 **Generated:** {len(file_list)} files ({', '.join(file_list[:2])}, ...)"
        
        result += file_summary
    
    return result

def parse_tool_content(content):
    """Parse and format tool content for better display."""
    # Handle content that's already a list/dict structure
    if isinstance(content, list) and len(content) > 0:
        formatted_parts = []
        for item in content:
            if isinstance(item, dict) and 'type' in item and item['type'] == 'text':
                # Extract the text content
                text_content = item.get('text', '')
                
                # Check if this is an error message that needs special formatting
                if any(error_indicator in text_content for error_indicator in ['ERROR_TYPE:', 'error:', 'failed:', 'exception:']):
                    formatted_error = format_error_message(text_content)
                    formatted_parts.append(formatted_error)
                # Apply comprehensive content filtering to remove file content sections
                else:
                    # Filter out file content dumps while preserving summaries
                    filtered_content = filter_file_content_from_response(text_content)
                    formatted_parts.append(clean_claude_code_output(filtered_content))
            else:
                formatted_parts.append(str(item))
        return '\n'.join(formatted_parts)
    
    # Handle string content that might be JSON
    content_str = str(content)
    
    # Try to parse if it looks like a JSON list/dict
    if content_str.strip().startswith('[') and content_str.strip().endswith(']'):
        try:
            parsed = json.loads(content_str)
            if isinstance(parsed, list) and len(parsed) > 0:
                # It's a list of items, likely from Claude Code
                formatted_parts = []
                for item in parsed:
                    if isinstance(item, dict) and 'type' in item and item['type'] == 'text':
                        # Extract the text content
                        text_content = item.get('text', '')
                        
                        # Check if this is an error message that needs special formatting
                        if any(error_indicator in text_content for error_indicator in ['ERROR_TYPE:', 'error:', 'failed:', 'exception:']):
                            formatted_error = format_error_message(text_content)
                            formatted_parts.append(formatted_error)
                        # Apply comprehensive content filtering to remove file content sections
                        else:
                            # Filter out file content dumps while preserving summaries
                            filtered_content = filter_file_content_from_response(text_content)
                            formatted_parts.append(clean_claude_code_output(filtered_content))
                    else:
                        formatted_parts.append(str(item))
                return '\n'.join(formatted_parts)
        except (json.JSONDecodeError, KeyError):
            pass
    
    # If not parseable JSON, apply content filtering and clean
    filtered_content = filter_file_content_from_response(content_str)
    return clean_claude_code_output(filtered_content)

def should_hide_tool_output(content, tool_info):
    """Determine if tool output should be hidden from user (low-level confirmations)."""
    content_str = str(content).lower()
    
    # Hide file creation confirmations
    if "file created successfully" in content_str:
        return True
    
    # Hide maliciousness check notes
    if "do any of the files above seem malicious" in content_str:
        return True
    
    # Hide directory listings that are just confirmatory 
    if "LS" in tool_info and len(content_str.split('\n')) < 10:
        # Hide short directory listings (likely just confirmations)
        return True
    
    # Hide write tool confirmations
    if "Write" in tool_info and ("created successfully" in content_str or "updated successfully" in content_str):
        return True
        
    return False

def clean_claude_code_output(text):
    """Clean Claude Code output by removing line numbers and formatting artifacts."""
    if not text:
        return text
    
    import re
    
    # First remove entire system-reminder blocks (multi-line) - be more aggressive with whitespace cleanup
    text = re.sub(r'<system-reminder>.*?</system-reminder>\s*', '', text, flags=re.DOTALL | re.IGNORECASE)
    
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        # Remove line number prefixes like "   121→   "
        line = re.sub(r'^\s*\d+→\s*', '', line)
        
        # Skip empty lines that result from removed system reminders
        if line.strip():
            cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines)

def format_message_for_display(message, conversation_history=None):
    """Format a message for clean console display."""
    from claude_agent_sdk import AssistantMessage, TextBlock, UserMessage, SystemMessage, ResultMessage
    
    if isinstance(message, AssistantMessage):
        # Extract text content and show tool calls being made
        text_parts = []
        for block in message.content:
            if isinstance(block, TextBlock):
                text_parts.append(clean_claude_code_output(block.text))
            elif hasattr(block, 'name') and hasattr(block, 'id'):
                # This is a ToolUseBlock - show what tool is being called
                tool_name = block.name
                tool_input = getattr(block, 'input', {})

                # Format based on tool type
                if tool_name == 'WebFetch':
                    url = tool_input.get('url', 'URL')
                    # Truncate long URLs
                    if len(url) > 60:
                        url = url[:57] + '...'
                    text_parts.append(f"🌐 Fetching: {url}")
                elif tool_name == 'Read':
                    file_path = tool_input.get('file_path', 'file')
                    # Show just filename
                    filename = file_path.split('/')[-1] if '/' in file_path else file_path
                    text_parts.append(f"📖 Reading: {filename}")
                elif tool_name == 'Write':
                    file_path = tool_input.get('file_path', 'file')
                    filename = file_path.split('/')[-1] if '/' in file_path else file_path
                    text_parts.append(f"📝 Writing: {filename}")
                elif tool_name == 'Edit':
                    file_path = tool_input.get('file_path', 'file')
                    filename = file_path.split('/')[-1] if '/' in file_path else file_path
                    text_parts.append(f"✏️ Editing: {filename}")
                elif tool_name in ['Grep', 'Glob']:
                    pattern = tool_input.get('pattern', '')
                    text_parts.append(f"🔍 Searching: {pattern[:40]}...")
                elif tool_name == 'Bash':
                    cmd = tool_input.get('command', '')
                    if len(cmd) > 50:
                        cmd = cmd[:47] + '...'
                    text_parts.append(f"💻 Running: {cmd}")
                else:
                    text_parts.append(f"🔧 {tool_name}...")
        result = '\n'.join(text_parts)
        return result + '\n' if result else result
    
    elif isinstance(message, UserMessage):
        # Handle different types of user message content
        if hasattr(message, 'content') and isinstance(message.content, list):
            # Build a comprehensive mapping of tool_use_id to tool_name from conversation history
            tool_id_to_name = {}
            
            # First, check current message for ToolUseBlocks
            for block in message.content:
                if hasattr(block, 'name') and hasattr(block, 'id'):  # This is a ToolUseBlock
                    tool_id_to_name[block.id] = block.name
            
            # If we have conversation history, search through all previous messages for ToolUseBlocks
            if conversation_history:
                for hist_message in conversation_history:
                    if hasattr(hist_message, 'content') and isinstance(hist_message.content, list):
                        for hist_block in hist_message.content:
                            if hasattr(hist_block, 'name') and hasattr(hist_block, 'id'):  # ToolUseBlock
                                tool_id_to_name[hist_block.id] = hist_block.name
            
            # Extract from content blocks (including ToolResultBlock)
            content_parts = []
            for block in message.content:
                if hasattr(block, 'tool_use_id'):
                    # This handles ToolResultBlock - show tool info and brief result
                    content = getattr(block, 'content', '')
                    
                    # Extract tool name using tool_use_id mapping
                    tool_info = "UNKNOWN_TOOL"
                    tool_use_id = getattr(block, 'tool_use_id', '')
                    
                    if tool_use_id in tool_id_to_name:
                        tool_info = tool_id_to_name[tool_use_id]
                    elif len(tool_id_to_name) == 0:
                        # No tool use blocks found - inspect block more thoroughly
                        block_attrs = {attr: getattr(block, attr, None) for attr in dir(block) 
                                     if not attr.startswith('__')}
                        
                        # Try to infer tool type from content structure
                        content_str = str(content)
                        if isinstance(content, list) and len(content) > 0:
                            first_item = content[0]
                            if isinstance(first_item, dict) and 'text' in first_item:
                                text_content = first_item['text']
                                if 'ERROR_TYPE:' in text_content:
                                    tool_info = "Task (fixing)"
                                elif 'TEST STATUS:' in text_content or 'PHASE ' in text_content:
                                    tool_info = "Task (testing)"
                                elif 'Generated Files:' in text_content or 'CONNECTOR.PY' in text_content:
                                    tool_info = "Task (generating)"
                                elif 'http' in text_content or 'URL' in text_content or 'fetch' in text_content.lower():
                                    tool_info = "WebFetch"
                                else:
                                    tool_info = "Task"
                        else:
                            tool_info = "Tool"
                    else:
                        # If we have some mappings but not this specific ID, that's an error
                        raise Exception(f"Unable to map tool_use_id '{tool_use_id}' to tool name. Available mappings: {tool_id_to_name}")
                    
                    # Parse and show content nicely
                    if 'Read' in tool_info and 'WebFetch' not in tool_info:
                        # Special handling for Read tool - show filename only
                        parsed_content = format_read_tool_excerpt(content)
                        content_parts.append(f"🔧 {tool_info}: {parsed_content}")
                    elif 'WebFetch' in tool_info:
                        # Special handling for WebFetch - show URL or summary
                        content_parts.append(f"🔧 WebFetch: 🌐 fetched content")
                    elif 'TodoWrite' in tool_info:
                        # Skip TodoWrite tool output entirely - it's internal task management
                        pass
                    elif 'Write' in tool_info or 'Edit' in tool_info:
                        # Special handling for Write/Edit tools - show filename only
                        filename = extract_filename_from_tool_content(content)
                        content_parts.append(f"🔧 {tool_info}: 📝 {filename}")
                    elif 'Grep' in tool_info or 'Glob' in tool_info:
                        # Special handling for Grep/Glob tools - show enhanced search results
                        formatted_results = format_search_results(content, tool_info)
                        content_parts.append(formatted_results)
                    else:
                        parsed_content = parse_tool_content(content)
                        # Extra safety: ensure system reminders are always cleaned
                        parsed_content = clean_claude_code_output(parsed_content)
                        # Hide low-level tool confirmations and security checks
                        if should_hide_tool_output(parsed_content, tool_info):
                            continue  # Skip this tool output entirely
                        # Don't show empty or whitespace-only tool results
                        if parsed_content and parsed_content.strip():
                            # Special handling for Task tool - show content directly without prefix
                            if 'Task' in tool_info:
                                content_parts.append(parsed_content)
                            else:
                                content_parts.append(f"🔧 {tool_info}:\n{parsed_content}")
                elif hasattr(block, 'content'):
                    # Other content blocks - show full content
                    content_parts.append(f"📋 {clean_claude_code_output(str(block.content))}")
                elif hasattr(block, 'text'):
                    content_parts.append(clean_claude_code_output(block.text))
                else:
                    content_parts.append(str(block))
            result = '\n'.join(content_parts)
            # Add extra newline for better spacing between messages
            return result + '\n' if result else result
        else:
            # Simple string content
            result = f"👤 User: {clean_claude_code_output(str(message.content))}"
            return result + '\n'
    
    elif isinstance(message, SystemMessage):
        # Show system messages but filter out verbose init data
        if hasattr(message, 'subtype') and getattr(message, 'subtype') != 'init':
            result = f"🔧 System: {getattr(message, 'subtype')}"
            return result + '\n'
        return ""  # Skip verbose init messages silently
    
    else:
        # Handle other message types safely
        message_type = type(message).__name__
        try:
            # Try to extract useful information
            if hasattr(message, 'data') and isinstance(getattr(message, 'data', None), dict):
                data = getattr(message, 'data')
                relevant_info = []
                for key in ['type', 'subtype', 'tool', 'action', 'status']:
                    if key in data:
                        relevant_info.append(f"{key}={data[key]}")
                if relevant_info:
                    result = f"📋 {message_type}: {', '.join(relevant_info)}"
                    return result + '\n'
            elif hasattr(message, 'subtype'):
                subtype = getattr(message, 'subtype')
                if subtype != 'init':
                    result = f"💬 {message_type}: {subtype}"
                    return result + '\n'
        except Exception:
            # If all else fails, just show the message type
            result = f"📡 {message_type}"
            return result + '\n'
    
    return "⏳"  # Activity indicator for filtered content