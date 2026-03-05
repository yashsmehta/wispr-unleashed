#!/bin/bash
# Toggle wispr-unleashed recording on/off.
# Designed to be triggered by a keyboard shortcut (Option+Shift+W).

PID_FILE="/tmp/wispr-unleashed.pid"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# ── If already running, stop it ──────────────────────────────────────────────
if [ -f "$PID_FILE" ]; then
    pid=$(cat "$PID_FILE")
    if kill -0 "$pid" 2>/dev/null; then
        kill -INT "$pid"
        exit 0
    fi
    rm -f "$PID_FILE"  # stale
fi

# ── Not running — open Terminal and start recording ──────────────────────────
osascript -e "
    tell application \"Terminal\"
        activate
        do script \"python3 '$ROOT_DIR/record.py'\"
    end tell
" 2>/dev/null
