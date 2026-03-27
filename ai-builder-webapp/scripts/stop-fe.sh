#!/bin/bash
# Stop the frontend server

PID_FILE="/tmp/csdk-frontend.pid"

# Kill all vite preview processes (npm + node + vite children)
PIDS=$(pgrep -f "vite preview")
if [ -n "$PIDS" ]; then
    echo "Stopping frontend processes: $PIDS"
    pkill -f "vite preview"
    sleep 2
    # Force kill any survivors
    PIDS=$(pgrep -f "vite preview")
    if [ -n "$PIDS" ]; then
        echo "Force killing: $PIDS"
        pkill -9 -f "vite preview"
    fi
    echo "Frontend stopped"
else
    echo "Frontend not running"
fi
rm -f "$PID_FILE"
