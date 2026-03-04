#!/bin/bash
# One-command installer for Wispr Unleashed.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

echo ""
echo "  ✦ Wispr Unleashed — installer"
echo ""

# ── Check Python ──────────────────────────────────────────────────────────────

if ! command -v python3 &>/dev/null; then
    echo "  ✗ Python 3 not found."
    echo "    Install it from https://www.python.org/downloads/"
    exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "  ✓ Python $PY_VERSION"

# ── Check Wispr Flow ──────────────────────────────────────────────────────────

WISPR_DB="$HOME/Library/Application Support/Wispr Flow/flow.sqlite"
if [ ! -f "$WISPR_DB" ]; then
    echo "  ✗ Wispr Flow not found."
    echo "    Install it from https://wispr.com and use it at least once."
    exit 1
fi
echo "  ✓ Wispr Flow"

# ── Install Python dependencies ───────────────────────────────────────────────

echo ""
echo "  Installing dependencies..."
pip3 install -q -r "$SCRIPT_DIR/requirements.txt"
echo "  ✓ Dependencies installed"

# ── API key ───────────────────────────────────────────────────────────────────

echo ""
if [ -f "$ENV_FILE" ] && grep -q "GOOGLE_API_KEY=." "$ENV_FILE" 2>/dev/null && ! grep -q "your-api-key-here" "$ENV_FILE" 2>/dev/null; then
    echo "  ✓ API key already configured"
else
    echo "  You need a free Google AI Studio API key."
    echo "  Get one here: https://aistudio.google.com/apikey"
    echo ""
    read -rp "  Paste your API key: " api_key

    if [ -z "$api_key" ]; then
        echo "  ✗ No API key provided. You can add it later to .env"
        cp -n "$SCRIPT_DIR/.env.example" "$ENV_FILE" 2>/dev/null || true
    else
        echo "GOOGLE_API_KEY=$api_key" > "$ENV_FILE"
        echo "  ✓ API key saved to .env"
    fi
fi

# ── Keyboard shortcut ─────────────────────────────────────────────────────────

echo ""
read -rp "  Set up keyboard shortcut (Option+Shift+W)? [Y/n] " shortcut
shortcut=${shortcut:-Y}

if [[ "$shortcut" =~ ^[Yy] ]]; then
    bash "$SCRIPT_DIR/setup.sh"
else
    echo "  Skipped. Run 'bash setup.sh' later if you change your mind."
fi

# ── Done ──────────────────────────────────────────────────────────────────────

echo ""
echo "  ✦ Ready! Start recording with:"
echo ""
echo "    python3 $SCRIPT_DIR/record.py \"Meeting Title\""
echo ""
echo "  Or use Option+Shift+W from anywhere."
echo ""
