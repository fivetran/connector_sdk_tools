#!/bin/bash
# Stop all CIC servers (backend and frontend)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Stopping all services..."
echo

"$SCRIPT_DIR/stop-be.sh"
"$SCRIPT_DIR/stop-fe.sh"

echo "All services stopped"
