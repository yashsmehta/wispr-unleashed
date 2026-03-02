#!/bin/bash
# Toggle wispr-clawd recording on/off.
# Designed to be triggered by a keyboard shortcut (Option+Shift+W).

PID_FILE="/tmp/wispr-clawd.pid"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="/tmp/wispr-clawd.log"

# ── If already running, stop it ──────────────────────────────────────────────
if [ -f "$PID_FILE" ]; then
    pid=$(cat "$PID_FILE")
    if kill -0 "$pid" 2>/dev/null; then
        kill -INT "$pid"
        osascript -e 'display notification "Meeting recording stopped" with title "Wispr Clawd"'
        exit 0
    fi
    rm -f "$PID_FILE"  # stale
fi

# ── Not running — prompt for title and start ─────────────────────────────────
title=$(osascript -e '
    text returned of (display dialog "Meeting title:" default answer "" with title "Wispr Clawd" buttons {"Cancel", "Start"} default button "Start")
' 2>/dev/null) || exit 0
[ -z "$title" ] && exit 0

# Start recording in background
: > "$LOG"
nohup python3 "$SCRIPT_DIR/record.py" "$title" >> "$LOG" 2>&1 &

osascript -e "display notification \"Recording: $title\" with title \"Wispr Clawd\""
