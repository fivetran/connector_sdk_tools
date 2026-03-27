#!/bin/bash
# Start the backend server

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_DIR/backend"
LOG_FILE="/tmp/csdk-backend.log"
PID_FILE="/tmp/csdk-backend.pid"

# Check if already running
if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "Backend is already running (PID: $(cat "$PID_FILE"))"
    exit 1
fi

# Start the backend
cd "$BACKEND_DIR"
source venv/bin/activate
nohup python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 > "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"

echo "Backend started (PID: $(cat "$PID_FILE"))"
echo "Logs: $LOG_FILE"
