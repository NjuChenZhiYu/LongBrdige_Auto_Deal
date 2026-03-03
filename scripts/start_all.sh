#!/bin/bash

# Navigate to project root directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# Check for virtual environment (priority: venv_auto_deal > venv)
if [ -d "venv_auto_deal" ]; then
    VENV_DIR="venv_auto_deal"
elif [ -d "venv" ]; then
    VENV_DIR="venv"
else
    echo "Error: Virtual environment not found! (Checked 'venv_auto_deal' and 'venv')"
    exit 1
fi

# Find Python executable
if [ -f "$VENV_DIR/bin/python3" ]; then
    PYTHON_EXEC="./$VENV_DIR/bin/python3"
elif [ -f "$VENV_DIR/bin/python" ]; then
    PYTHON_EXEC="./$VENV_DIR/bin/python"
else
    echo "Error: Python executable not found in $VENV_DIR/bin/"
    exit 1
fi
echo "Using Python: $PYTHON_EXEC"

# Ensure logs directory exists
mkdir -p logs

# Set PYTHONPATH
export PYTHONPATH=$PYTHONPATH:.

# Start Watchlist Monitor Service
echo "Starting Watchlist Monitor Service..."
nohup $PYTHON_EXEC -m src.monitor.watchlist_monitor > logs/monitor.log 2>&1 &
MONITOR_PID=$!
echo "Monitor Service started with PID: $MONITOR_PID (Log: logs/monitor.log)"

# Start Web Interface
echo "Starting Web Interface..."
nohup $PYTHON_EXEC src/web/app.py > logs/web.log 2>&1 &
WEB_PID=$!
echo "Web Interface started with PID: $WEB_PID (Log: logs/web.log)"

# Save PIDs to file for easier stopping
echo "$MONITOR_PID" > logs/monitor.pid
echo "$WEB_PID" > logs/web.pid

# Try to get the server's IP address
SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
if [ -z "$SERVER_IP" ]; then
    SERVER_IP="<your_server_ip>"
fi

echo "All services started successfully!"
echo "Web Interface available at: http://$SERVER_IP:5001"
