#!/bin/bash
# Restart the backend server

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"$SCRIPT_DIR/stop-be.sh"
sleep 1
"$SCRIPT_DIR/start-be.sh"
