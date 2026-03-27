#!/bin/bash
# Start the frontend server (serves built files)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
FRONTEND_DIR="$PROJECT_DIR/frontend"
LOG_FILE="/tmp/csdk-frontend.log"
PID_FILE="/tmp/csdk-frontend.pid"

# Check if already running
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "Frontend is already running (PID: $(cat "$PID_FILE"))"
    exit 1
fi

# Start the frontend development server
cd "$FRONTEND_DIR"
nohup npm run dev -- --host 127.0.0.1 --port 5173 > "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"

echo "Frontend started (PID: $(cat "$PID_FILE"))"
echo "Logs: $LOG_FILE"
