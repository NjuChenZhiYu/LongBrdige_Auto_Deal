#!/bin/bash

# Navigate to project root directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "Error: Virtual environment (venv) not found!"
    exit 1
fi

# Ensure logs directory exists
mkdir -p logs

# Set PYTHONPATH
export PYTHONPATH=$PYTHONPATH:.

# Start Watchlist Monitor Service
echo "Starting Watchlist Monitor Service..."
nohup ./venv/bin/python3 -m src.monitor.watchlist_monitor > logs/monitor.log 2>&1 &
MONITOR_PID=$!
echo "Monitor Service started with PID: $MONITOR_PID (Log: logs/monitor.log)"

# Start Web Interface
echo "Starting Web Interface..."
nohup ./venv/bin/python3 src/web/app.py > logs/web.log 2>&1 &
WEB_PID=$!
echo "Web Interface started with PID: $WEB_PID (Log: logs/web.log)"

# Save PIDs to file for easier stopping
echo "$MONITOR_PID" > logs/monitor.pid
echo "$WEB_PID" > logs/web.pid

echo "All services started successfully!"
echo "Web Interface available at: http://127.0.0.1:5001"
