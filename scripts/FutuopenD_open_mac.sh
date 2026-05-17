#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

DEFAULT_OPEND_DIR="/Users/chenzhiyu/Documents/Futu_OpenD_10.4.6408_Mac/Futu_OpenD_10.4.6408_Mac"
OPEND_DIR="${OPEND_DIR:-$DEFAULT_OPEND_DIR}"
APP_PATH="${APP_PATH:-$OPEND_DIR/FutuOpenD.app}"
BIN_PATH="${BIN_PATH:-$APP_PATH/Contents/MacOS/FutuOpenD}"
CFG_FILE="${CFG_FILE:-$OPEND_DIR/FutuOpenD.xml}"
FIXRUN_SH="${FIXRUN_SH:-$OPEND_DIR/fixrun.sh}"
API_PORT="${API_PORT:-11111}"
STARTUP_WAIT_SECONDS="${STARTUP_WAIT_SECONDS:-15}"

LOG_DIR="$PROJECT_ROOT/logs"
LOG_FILE="$LOG_DIR/futuopend.log"
PID_FILE="$LOG_DIR/futuopend.pid"

mkdir -p "$LOG_DIR"

is_port_listening() {
    lsof -nP -iTCP:"$API_PORT" -sTCP:LISTEN >/dev/null 2>&1
}

print_error_and_exit() {
    echo "Error: $1" >&2
    exit 1
}

if [ ! -d "$APP_PATH" ]; then
    print_error_and_exit "FutuOpenD.app not found: $APP_PATH"
fi

if [ ! -x "$BIN_PATH" ]; then
    print_error_and_exit "FutuOpenD binary not executable or missing: $BIN_PATH"
fi

if [ ! -f "$CFG_FILE" ]; then
    print_error_and_exit "FutuOpenD.xml not found: $CFG_FILE"
fi

echo "Using OpenD dir : $OPEND_DIR"
echo "Using app       : $APP_PATH"
echo "Using binary    : $BIN_PATH"
echo "Using config    : $CFG_FILE"
echo "Using API port  : $API_PORT"

if is_port_listening; then
    echo "FutuOpenD is already listening on port $API_PORT."
    exit 0
fi

# Best effort: remove quarantine markers so macOS can resolve app paths normally.
if [ -f "$FIXRUN_SH" ]; then
    echo "Running fixrun.sh..."
    sh "$FIXRUN_SH" "$OPEND_DIR" || echo "Warning: fixrun.sh returned non-zero, continuing..."
fi

echo "Removing com.apple.quarantine (best effort)..."
xattr -r -d com.apple.quarantine "$APP_PATH" >/dev/null 2>&1 || true

if [ -f "$PID_FILE" ]; then
    OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [ -n "${OLD_PID:-}" ] && kill -0 "$OLD_PID" >/dev/null 2>&1; then
        echo "Stopping stale FutuOpenD process (PID: $OLD_PID)..."
        kill "$OLD_PID" >/dev/null 2>&1 || true
        sleep 1
    fi
    rm -f "$PID_FILE"
fi

echo "Starting FutuOpenD in background..."
nohup "$BIN_PATH" -cfg_file="$CFG_FILE" > "$LOG_FILE" 2>&1 &
OPEND_PID=$!
echo "$OPEND_PID" > "$PID_FILE"
echo "FutuOpenD started with PID: $OPEND_PID"
echo "Log file: $LOG_FILE"

for ((i=1; i<=STARTUP_WAIT_SECONDS; i++)); do
    if is_port_listening; then
        echo "FutuOpenD is now listening on port $API_PORT."
        exit 0
    fi

    if ! kill -0 "$OPEND_PID" >/dev/null 2>&1; then
        echo "FutuOpenD exited early. Recent logs:"
        tail -n 50 "$LOG_FILE" 2>/dev/null || true
        exit 1
    fi

    sleep 1
done

echo "FutuOpenD process is running, but port $API_PORT is still not listening after ${STARTUP_WAIT_SECONDS}s."
echo "Recent logs:"
tail -n 50 "$LOG_FILE" 2>/dev/null || true
exit 1
