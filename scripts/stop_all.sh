#!/bin/bash

# Navigate to project root directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# Stop Monitor Service
if [ -f "logs/monitor.pid" ]; then
    PID=$(cat logs/monitor.pid)
    echo "Stopping Monitor Service (PID: $PID)..."
    kill $PID 2>/dev/null
    rm logs/monitor.pid
else
    echo "Monitor Service PID file not found. Checking processes..."
    PIDS=$(ps aux | grep "src.monitor.watchlist_monitor" | grep -v grep | awk '{print $2}')
    if [ -n "$PIDS" ]; then
        echo "Found running Monitor Service processes: $PIDS. Killing..."
        echo "$PIDS" | xargs kill
    else
        echo "No running Monitor Service process found."
    fi
fi

# Stop Web Interface
if [ -f "logs/web.pid" ]; then
    PID=$(cat logs/web.pid)
    echo "Stopping Web Interface (PID: $PID)..."
    kill $PID 2>/dev/null
    rm logs/web.pid
else
    echo "Web Interface PID file not found. Checking processes..."
    PIDS=$(ps aux | grep "src/web/app.py" | grep -v grep | awk '{print $2}')
    if [ -n "$PIDS" ]; then
        echo "Found running Web Interface processes: $PIDS. Killing..."
        echo "$PIDS" | xargs kill
    else
        echo "No running Web Interface process found."
    fi
fi

echo "All services stopped."
