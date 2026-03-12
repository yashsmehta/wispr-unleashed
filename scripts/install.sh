#!/bin/bash
# Installer for Wispr Unleashed.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"

# ── ANSI ─────────────────────────────────────────────────────────────────────

DIM='\033[2m'
BOLD='\033[1m'
GREEN='\033[32m'
YELLOW='\033[33m'
CYAN='\033[36m'
RESET='\033[0m'

ok()   { echo -e "  ${GREEN}✓${RESET}  $1"; }
warn() { echo -e "  ${YELLOW}⚠${RESET}  $1"; }
fail() { echo -e "  ${YELLOW}✗${RESET}  $1"; }
dim()  { echo -e "  ${DIM}$1${RESET}"; }

# ── Header ───────────────────────────────────────────────────────────────────

echo ""
echo -e "  ${BOLD}✦ wispr unleashed${RESET}"
echo ""

# ── Check Python ─────────────────────────────────────────────────────────────

if ! command -v python3 &>/dev/null; then
    fail "python 3 not found"
    dim "   install from https://www.python.org/downloads/"
    exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
ok "python $PY_VERSION"

# ── Check Wispr Flow ─────────────────────────────────────────────────────────

WISPR_DB="$HOME/Library/Application Support/Wispr Flow/flow.sqlite"
if [ ! -f "$WISPR_DB" ]; then
    fail "wispr flow not found"
    dim "   install from https://wispr.com and do one test recording"
    exit 1
fi
ok "wispr flow"

# ── Install Python dependencies ──────────────────────────────────────────────

echo ""
dim "installing dependencies…"
pip3 install -q -r "$ROOT_DIR/requirements.txt"
ok "dependencies installed"

# ── Gemini API ───────────────────────────────────────────────────────────────

echo ""

if [ -f "$ENV_FILE" ]; then
    if grep -q "GOOGLE_API_KEY=" "$ENV_FILE" 2>/dev/null || \
       grep -q "GEMINI_API_KEY=" "$ENV_FILE" 2>/dev/null; then
        ok "gemini API key configured"
    elif grep -q "GOOGLE_GENAI_USE_VERTEXAI=True" "$ENV_FILE" 2>/dev/null; then
        ok "vertex AI configured"
    fi
else
    echo -e "  ${DIM}gemini authentication${RESET}"
    echo ""
    echo -e "     ${CYAN}1${RESET}  API key ${DIM}— simple, free tier available${RESET}"
    echo -e "     ${CYAN}2${RESET}  Vertex AI ${DIM}— Google Cloud SDK credentials${RESET}"
    echo ""
    read -rp "  choice [1]: " auth_choice
    auth_choice=${auth_choice:-1}

    if [[ "$auth_choice" == "2" ]]; then
        echo "GOOGLE_GENAI_USE_VERTEXAI=True" > "$ENV_FILE"
        ok "vertex AI enabled"

        if ! command -v gcloud &>/dev/null && [ ! -f "$HOME/google-cloud-sdk/bin/gcloud" ]; then
            echo ""
            warn "Google Cloud SDK not found"
            dim "   install: https://cloud.google.com/sdk/docs/install"
            dim "   then run: gcloud auth application-default login"
        else
            GCLOUD_CMD="gcloud"
            [ -f "$HOME/google-cloud-sdk/bin/gcloud" ] && GCLOUD_CMD="$HOME/google-cloud-sdk/bin/gcloud"
            if ! "$GCLOUD_CMD" auth application-default print-access-token &>/dev/null; then
                echo ""
                warn "GCP credentials not set up"
                dim "   run: $GCLOUD_CMD auth application-default login"
            else
                ok "GCP credentials"
            fi
        fi
    else
        echo ""
        dim "get a free key at: https://aistudio.google.com/apikey"
        echo ""
        read -rp "  paste your API key: " api_key
        if [ -n "$api_key" ]; then
            echo "GOOGLE_API_KEY=$api_key" > "$ENV_FILE"
            ok "API key saved"
        else
            warn "no key entered"
            dim "   add GOOGLE_API_KEY=your-key to .env later"
            touch "$ENV_FILE"
        fi
    fi
fi

# ── Shell command ────────────────────────────────────────────────────────────

SHELL_NAME="$(basename "$SHELL")"
if [ "$SHELL_NAME" = "zsh" ]; then
    RC_FILE="$HOME/.zshrc"
elif [ "$SHELL_NAME" = "bash" ]; then
    RC_FILE="$HOME/.bashrc"
else
    RC_FILE=""
fi

WISPR_FUNC='wispr() {
  python3 '"$ROOT_DIR"'/record.py "$*"
}'

echo ""

if [ -n "$RC_FILE" ] && grep -q 'wispr()' "$RC_FILE" 2>/dev/null; then
    ok "wispr command already set up"
else
    echo -e "  ${DIM}add${RESET} ${BOLD}wispr${RESET} ${DIM}command to your shell?${RESET}"
    dim "lets you run: wispr \"Meeting Title\""
    echo ""
    read -rp "  add to $RC_FILE? [Y/n]: " add_alias
    add_alias=${add_alias:-Y}

    if [[ "$add_alias" =~ ^[Yy] ]]; then
        if [ -n "$RC_FILE" ]; then
            echo "" >> "$RC_FILE"
            echo "$WISPR_FUNC" >> "$RC_FILE"
            ok "wispr command added to ${RC_FILE/$HOME/~}"
        else
            warn "couldn't detect shell config"
            dim "   add this to your shell config manually:"
            echo ""
            echo "    $WISPR_FUNC"
        fi
    else
        dim "skipped — you can always run directly:"
        dim "python3 $ROOT_DIR/record.py \"Meeting Title\""
    fi
fi

# ── Done ─────────────────────────────────────────────────────────────────────

echo ""
echo -e "  ${GREEN}●${RESET} ${BOLD}ready${RESET}"
echo ""
if [ -n "$RC_FILE" ] && grep -q 'wispr()' "$RC_FILE" 2>/dev/null; then
    dim "start recording:"
    echo ""
    echo -e "     ${BOLD}wispr${RESET} ${DIM}\"Meeting Title\"${RESET}"
    echo ""
    dim "restart your terminal or run: source ${RC_FILE/$HOME/~}"
else
    dim "start recording:"
    echo ""
    echo -e "     ${BOLD}python3 $ROOT_DIR/record.py${RESET} ${DIM}\"Meeting Title\"${RESET}"
fi
echo ""
