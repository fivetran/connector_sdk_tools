#!/bin/bash
# Check if backend and frontend are running

check_service() {
    local name=$1
    local pid_file=$2
    local process_pattern=$3

    if [ -f "$pid_file" ]; then
        PID=$(cat "$pid_file")
        if kill -0 "$PID" 2>/dev/null; then
            echo "$name: RUNNING (PID: $PID)"
            return 0
        else
            echo "$name: NOT RUNNING (stale PID file)"
            rm -f "$pid_file"
            return 1
        fi
    else
        # Check by process name
        PIDS=$(pgrep -f "$process_pattern")
        if [ -n "$PIDS" ]; then
            echo "$name: RUNNING (PID: $PIDS)"
            return 0
        else
            echo "$name: NOT RUNNING"
            return 1
        fi
    fi
}

echo "=== CSDK AI Status ==="
echo ""

check_service "Backend " "/tmp/csdk-backend.pid" "uvicorn app.main:app"
BE_STATUS=$?

check_service "Frontend" "/tmp/csdk-frontend.pid" "vite preview"
FE_STATUS=$?

echo ""

# Exit with error if either is not running
if [ $BE_STATUS -ne 0 ] || [ $FE_STATUS -ne 0 ]; then
    exit 1
fi
exit 0
