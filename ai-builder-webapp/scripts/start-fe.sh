#!/bin/bash
# Start the frontend server (serves built files)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
FRONTEND_DIR="$PROJECT_DIR/frontend"
LOG_FILE="/tmp/csdk-frontend.log"
PID_FILE="/tmp/csdk-frontend.pid"

# Kill any existing vite preview processes
EXISTING=$(pgrep -f "vite preview")
if [ -n "$EXISTING" ]; then
    echo "Stopping existing frontend processes: $EXISTING"
    pkill -f "vite preview"
    sleep 2
    pkill -9 -f "vite preview" 2>/dev/null
fi

# Start the frontend preview server
cd "$FRONTEND_DIR"
nohup npm run preview -- --host 127.0.0.1 --port 5173 > "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"

echo "Frontend started (PID: $(cat "$PID_FILE"))"
echo "Logs: $LOG_FILE"
