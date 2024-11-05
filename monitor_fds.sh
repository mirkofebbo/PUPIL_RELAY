#!/bin/bash

# monitor_fds.sh

PROCESS_NAME="main.py"

while true; do
    PID=$(pgrep -f $PROCESS_NAME)
    if [ -z "$PID" ]; then
        echo "$(date): Process $PROCESS_NAME not running."
    else
        FD_COUNT=$(lsof -p $PID | wc -l)
        echo "$(date): Open file descriptors for $PROCESS_NAME (PID $PID): $FD_COUNT"
    fi
    sleep 60  # Check every minute
done
