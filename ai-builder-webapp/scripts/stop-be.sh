#!/bin/bash
# Stop the backend server

PID_FILE="/tmp/csdk-backend.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "Stopping backend (PID: $PID)..."
        kill "$PID"
        sleep 2
        # Force kill if still running
        if kill -0 "$PID" 2>/dev/null; then
            echo "Force killing..."
            kill -9 "$PID"
        fi
        echo "Backend stopped"
    else
        echo "Backend not running (stale PID file)"
    fi
    rm -f "$PID_FILE"
else
    # Try to find and kill by process name
    PIDS=$(pgrep -f "uvicorn app.main:app")
    if [ -n "$PIDS" ]; then
        echo "Stopping backend processes: $PIDS"
        pkill -f "uvicorn app.main:app"
        echo "Backend stopped"
    else
        echo "Backend not running"
    fi
fi
