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

# ── GCP / Vertex AI ──────────────────────────────────────────────────────────

echo ""
if [ -f "$ENV_FILE" ] && grep -q "GOOGLE_GENAI_USE_VERTEXAI=True" "$ENV_FILE" 2>/dev/null; then
    echo "  ✓ Vertex AI already configured"
else
    echo "GOOGLE_GENAI_USE_VERTEXAI=True" > "$ENV_FILE"
    echo "  ✓ Vertex AI enabled in .env"
fi

# Check for gcloud + application default credentials
if ! command -v gcloud &>/dev/null && [ ! -f "$HOME/google-cloud-sdk/bin/gcloud" ]; then
    echo ""
    echo "  ⚠ Google Cloud SDK not found."
    echo "    Install it: https://cloud.google.com/sdk/docs/install"
    echo "    Then run: gcloud auth application-default login"
else
    GCLOUD_CMD="gcloud"
    [ -f "$HOME/google-cloud-sdk/bin/gcloud" ] && GCLOUD_CMD="$HOME/google-cloud-sdk/bin/gcloud"
    if ! "$GCLOUD_CMD" auth application-default print-access-token &>/dev/null; then
        echo ""
        echo "  ⚠ GCP credentials not set up."
        echo "    Run: $GCLOUD_CMD auth application-default login"
    else
        echo "  ✓ GCP credentials"
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
