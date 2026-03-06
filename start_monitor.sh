#!/bin/bash
# Start script for Stock Monitor System

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Set PYTHONPATH
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"

# Kill existing processes
echo "Stopping existing processes..."
pkill -f "watchlist_monitor" 2>/dev/null
pkill -f "src/web/app.py" 2>/dev/null
sleep 2

# Kill forcefully if still running
pkill -9 -f "watchlist_monitor" 2>/dev/null
pkill -9 -f "src/web/app.py" 2>/dev/null
sleep 1

echo "Starting Watchlist Monitor..."
nohup ./venv/bin/python3 -m src.monitor.watchlist_monitor > /tmp/watchlist_monitor.log 2>&1 &
sleep 3

echo "Starting Web App..."
nohup ./venv/bin/python3 src/web/app.py > /tmp/app.log 2>&1 &
sleep 3

echo "Services started:"
ps aux | grep -E "watchlist_monitor|app\.py" | grep -v grep | grep -v start_monitor.sh
echo ""
echo "Logs:"
echo "  - Watchlist Monitor: tail -f /tmp/watchlist_monitor.log"
echo "  - Web App: tail -f /tmp/app.log"
