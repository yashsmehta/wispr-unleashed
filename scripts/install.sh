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

# ── LLM for note generation ─────────────────────────────────────────────────

echo ""

# Check if already configured
HAS_CONFIG=false
if [ -f "$ENV_FILE" ]; then
    if grep -qE "(OPENAI_API_KEY|ANTHROPIC_API_KEY|GOOGLE_API_KEY|GEMINI_API_KEY)=" "$ENV_FILE" 2>/dev/null; then
        MODEL=$(grep "^LLM_MODEL=" "$ENV_FILE" 2>/dev/null | cut -d= -f2)
        ok "LLM configured${MODEL:+ ($MODEL)}"
        HAS_CONFIG=true
    elif grep -q "GOOGLE_GENAI_USE_VERTEXAI=True" "$ENV_FILE" 2>/dev/null; then
        ok "vertex AI configured"
        HAS_CONFIG=true
    fi
fi

if [ "$HAS_CONFIG" = false ]; then
    echo -e "  ${DIM}note generation — pick your LLM provider${RESET}"
    echo ""
    echo -e "     ${CYAN}1${RESET}  Google Gemini ${DIM}— free tier available${RESET}"
    echo -e "     ${CYAN}2${RESET}  OpenAI"
    echo -e "     ${CYAN}3${RESET}  Anthropic"
    echo -e "     ${CYAN}4${RESET}  Skip ${DIM}— configure later in .env${RESET}"
    echo ""
    read -rp "  choice [1]: " provider
    provider=${provider:-1}

    case "$provider" in
        1)
            dim "get a free key at: https://aistudio.google.com/apikey"
            echo ""
            read -rp "  paste your API key: " api_key
            if [ -n "$api_key" ]; then
                echo "GOOGLE_API_KEY=$api_key" > "$ENV_FILE"
                echo "LLM_MODEL=gemini/gemini-3.1-pro" >> "$ENV_FILE"
                ok "gemini configured"
            else
                warn "no key entered — add GOOGLE_API_KEY to .env later"
                touch "$ENV_FILE"
            fi
            ;;
        2)
            dim "get a key at: https://platform.openai.com/api-keys"
            echo ""
            read -rp "  paste your API key: " api_key
            if [ -n "$api_key" ]; then
                echo "OPENAI_API_KEY=$api_key" > "$ENV_FILE"
                echo "LLM_MODEL=gpt-4o-mini" >> "$ENV_FILE"
                ok "openai configured"
            else
                warn "no key entered — add OPENAI_API_KEY to .env later"
                touch "$ENV_FILE"
            fi
            ;;
        3)
            dim "get a key at: https://console.anthropic.com/settings/keys"
            echo ""
            read -rp "  paste your API key: " api_key
            if [ -n "$api_key" ]; then
                echo "ANTHROPIC_API_KEY=$api_key" > "$ENV_FILE"
                echo "LLM_MODEL=anthropic/claude-sonnet-4-20250514" >> "$ENV_FILE"
                ok "anthropic configured"
            else
                warn "no key entered — add ANTHROPIC_API_KEY to .env later"
                touch "$ENV_FILE"
            fi
            ;;
        *)
            dim "skipped — edit .env when ready (see README for options)"
            touch "$ENV_FILE"
            ;;
    esac
fi

# ── Obsidian vault ──────────────────────────────────────────────────────────

echo ""

# Check if already configured in .env
EXISTING_VAULT=""
if [ -f "$ENV_FILE" ]; then
    EXISTING_VAULT=$(grep "^OBSIDIAN_VAULT=" "$ENV_FILE" 2>/dev/null | cut -d= -f2)
fi

if [ -n "$EXISTING_VAULT" ]; then
    EVAL_VAULT=$(eval echo "$EXISTING_VAULT" 2>/dev/null || echo "$EXISTING_VAULT")
    if [ -d "$EVAL_VAULT" ]; then
        ok "obsidian vault → ${EXISTING_VAULT/$HOME/~}"
    else
        warn "vault path not found: ${EXISTING_VAULT/$HOME/~}"
    fi
else
    echo -e "  ${BOLD}obsidian vault${RESET}"
    dim "your notes and transcripts will be saved here"
    echo ""
    echo -e "     ${CYAN}1${RESET}  Scan my Mac ${DIM}— auto-detect vault locations${RESET}"
    echo -e "     ${CYAN}2${RESET}  Enter path  ${DIM}— I know where my vault is${RESET}"
    echo -e "     ${CYAN}3${RESET}  Skip        ${DIM}— configure later in .env${RESET}"
    echo ""
    read -rp "  choice [1]: " vault_method
    vault_method=${vault_method:-1}

    case "$vault_method" in
        1)
            echo ""
            dim "scanning…"

            DETECTED_VAULTS=()

            # Check common locations first
            for candidate in \
                "$HOME/Desktop/Obsidian Vault" \
                "$HOME/Documents/Obsidian Vault" \
                "$HOME/Obsidian" \
                "$HOME/Documents/Obsidian" \
                "$HOME/Desktop/Obsidian"; do
                if [ -d "$candidate" ] && [ -d "$candidate/.obsidian" ]; then
                    DETECTED_VAULTS+=("$candidate")
                fi
            done

            # Deep scan Desktop, Documents, and Home
            for dir in "$HOME/Desktop" "$HOME/Documents" "$HOME"; do
                if [ -d "$dir" ]; then
                    while IFS= read -r vault_dir; do
                        vault_parent="$(dirname "$vault_dir")"
                        already=false
                        for v in "${DETECTED_VAULTS[@]}"; do
                            if [ "$v" = "$vault_parent" ]; then
                                already=true
                                break
                            fi
                        done
                        if [ "$already" = false ]; then
                            DETECTED_VAULTS+=("$vault_parent")
                        fi
                    done < <(find "$dir" -maxdepth 3 -name ".obsidian" -type d 2>/dev/null)
                fi
            done

            if [ ${#DETECTED_VAULTS[@]} -eq 0 ]; then
                echo ""
                warn "no vaults found"
                dim "   enter the path to your Obsidian vault"
                echo ""
                read -rp "  vault path: " manual_path
                if [ -n "$manual_path" ]; then
                    EVAL_PATH=$(eval echo "$manual_path" 2>/dev/null || echo "$manual_path")
                    if [ -d "$EVAL_PATH" ]; then
                        CHOSEN_VAULT="$EVAL_PATH"
                    else
                        echo ""
                        read -rp "  doesn't exist yet — create it? [Y/n]: " create_vault
                        create_vault=${create_vault:-Y}
                        if [[ "$create_vault" =~ ^[Yy] ]]; then
                            mkdir -p "$EVAL_PATH"
                            CHOSEN_VAULT="$EVAL_PATH"
                            ok "created ${manual_path/$HOME/~}"
                        fi
                    fi
                fi

            elif [ ${#DETECTED_VAULTS[@]} -eq 1 ]; then
                VAULT="${DETECTED_VAULTS[0]}"
                echo ""
                echo -e "     ${GREEN}●${RESET}  ${VAULT/$HOME/~}"
                echo ""
                read -rp "  use this vault? [Y/n]: " use_detected
                use_detected=${use_detected:-Y}
                if [[ "$use_detected" =~ ^[Yy] ]]; then
                    CHOSEN_VAULT="$VAULT"
                fi

            else
                echo ""
                dim "found ${#DETECTED_VAULTS[@]} vaults:"
                echo ""
                i=1
                for v in "${DETECTED_VAULTS[@]}"; do
                    echo -e "     ${CYAN}$i${RESET}  ${v/$HOME/~}"
                    i=$((i + 1))
                done
                echo ""
                read -rp "  choice [1]: " vault_choice
                vault_choice=${vault_choice:-1}
                if [ "$vault_choice" -ge 1 ] && [ "$vault_choice" -le "${#DETECTED_VAULTS[@]}" ] 2>/dev/null; then
                    CHOSEN_VAULT="${DETECTED_VAULTS[$((vault_choice - 1))]}"
                fi
            fi
            ;;

        2)
            echo ""
            dim "enter the full path (tab completion works)"
            dim "example: ~/Documents/My Notes"
            echo ""
            read -rep "  vault path: " manual_path
            if [ -n "$manual_path" ]; then
                EVAL_PATH=$(eval echo "$manual_path" 2>/dev/null || echo "$manual_path")
                if [ -d "$EVAL_PATH" ]; then
                    CHOSEN_VAULT="$EVAL_PATH"
                else
                    echo ""
                    read -rp "  doesn't exist yet — create it? [Y/n]: " create_vault
                    create_vault=${create_vault:-Y}
                    if [[ "$create_vault" =~ ^[Yy] ]]; then
                        mkdir -p "$EVAL_PATH"
                        CHOSEN_VAULT="$EVAL_PATH"
                        ok "created ${manual_path/$HOME/~}"
                    fi
                fi
            fi
            ;;

        *)
            dim "skipped — set OBSIDIAN_VAULT in .env when ready"
            ;;
    esac

    # Ask for name (used in note generation for context)
    if [ -n "${CHOSEN_VAULT:-}" ]; then
        echo ""
        read -rp "  your first name: " user_name
    fi

    # Write vault config and create Transcripts dir
    if [ -n "${CHOSEN_VAULT:-}" ]; then
        VAULT_SHORT="${CHOSEN_VAULT/$HOME/~}"

        if [ -f "$ENV_FILE" ]; then
            echo "OBSIDIAN_VAULT=$VAULT_SHORT" >> "$ENV_FILE"
        else
            echo "OBSIDIAN_VAULT=$VAULT_SHORT" > "$ENV_FILE"
        fi

        if [ -n "${user_name:-}" ]; then
            echo "USER_NAME=$user_name" >> "$ENV_FILE"
        fi

        # Create Transcripts folder
        TRANSCRIPTS_DIR="$CHOSEN_VAULT/Transcripts"
        if [ ! -d "$TRANSCRIPTS_DIR" ]; then
            mkdir -p "$TRANSCRIPTS_DIR"
        fi

        echo ""
        ok "vault → ${VAULT_SHORT}"
        dim "transcripts → ${VAULT_SHORT}/Transcripts"
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
    read -rp "  add to ${RC_FILE/$HOME/~}? [Y/n]: " add_alias
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
