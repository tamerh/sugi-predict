#!/bin/bash
#
# Stop Qdrant running on local storage
#

LOCAL_STORAGE="/localscratch/tgur/qdrant_test"
PID_FILE="$LOCAL_STORAGE/qdrant.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "No Qdrant PID file found at: $PID_FILE"
    echo "Qdrant may not be running"
    exit 0
fi

PID=$(cat "$PID_FILE")

if ps -p $PID > /dev/null 2>&1; then
    echo "Stopping Qdrant (PID: $PID)..."
    kill $PID
    sleep 2

    if ps -p $PID > /dev/null 2>&1; then
        echo "Force killing Qdrant..."
        kill -9 $PID
    fi

    echo "✓ Qdrant stopped"
else
    echo "Qdrant (PID: $PID) is not running"
fi

rm -f "$PID_FILE"
