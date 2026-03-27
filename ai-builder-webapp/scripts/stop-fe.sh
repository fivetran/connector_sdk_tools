#!/bin/bash
# Stop the frontend server

PID_FILE="/tmp/csdk-frontend.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "Stopping frontend (PID: $PID)..."
        kill "$PID"
        sleep 2
        # Force kill if still running
        if kill -0 "$PID" 2>/dev/null; then
            echo "Force killing..."
            kill -9 "$PID"
        fi
        echo "Frontend stopped"
    else
        echo "Frontend not running (stale PID file)"
    fi
    rm -f "$PID_FILE"
else
    # Try to find and kill by process name
    PIDS=$(pgrep -f "vite preview")
    if [ -n "$PIDS" ]; then
        echo "Stopping frontend processes: $PIDS"
        pkill -f "vite preview"
        echo "Frontend stopped"
    else
        echo "Frontend not running"
    fi
fi
