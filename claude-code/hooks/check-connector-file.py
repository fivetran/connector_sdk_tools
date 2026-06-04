#!/usr/bin/env python3
import sys
import json
import os
import datetime

CONNECTOR_FILES = ("connector.py", "configuration.json", "requirements.txt")
DEBUG_LOG = "/tmp/fivetran-hook-debug.log"


def main():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
        file_path = data.get("tool_input", {}).get("file_path", "")
        matched = os.path.basename(file_path) in CONNECTOR_FILES

        with open(DEBUG_LOG, "a") as f:
            f.write(f"[{datetime.datetime.now().isoformat()}] "
                    f"CLAUDE_PLUGIN_ROOT={os.environ.get('CLAUDE_PLUGIN_ROOT', 'NOT_SET')} "
                    f"file={file_path!r} matched={matched}\n")

        if matched:
            print(json.dumps({
                "additionalContext": "Tip: run /test-connector to verify your connector changes."
            }))
    except Exception as e:
        with open(DEBUG_LOG, "a") as f:
            f.write(f"[{datetime.datetime.now().isoformat()}] ERROR: {e}\n")


if __name__ == "__main__":
    main()
