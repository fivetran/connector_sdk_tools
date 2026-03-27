#!/bin/bash
# Tail backend logs

LOG_FILE="/tmp/csdk-backend.log"

if [ -f "$LOG_FILE" ]; then
    tail -f "$LOG_FILE"
else
    echo "No backend log file found at $LOG_FILE"
    echo "Is the backend running?"
fi
