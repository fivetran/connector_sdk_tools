#!/bin/bash
# Tail frontend logs

LOG_FILE="/tmp/csdk-frontend.log"

if [ -f "$LOG_FILE" ]; then
    tail -f "$LOG_FILE"
else
    echo "No frontend log file found at $LOG_FILE"
    echo "Is the frontend running?"
fi
