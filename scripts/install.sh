#!/bin/bash
# Interactive installer for Wispr Unleashed.

set -eo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"
umask 077

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

set_env() {
    key="$1"
    value="$2"
    temp_file="$ENV_FILE.tmp.$$"
    if [ -f "$ENV_FILE" ]; then
        awk -v key="$key" 'index($0, key "=") != 1 { print }' "$ENV_FILE" > "$temp_file"
    else
        : > "$temp_file"
    fi
    printf '%s=%s\n' "$key" "$value" >> "$temp_file"
    mv "$temp_file" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
}

get_env() {
    key="$1"
    [ -f "$ENV_FILE" ] || return 0
    awk -v key="$key" 'index($0, key "=") == 1 { print substr($0, length(key) + 2); exit }' "$ENV_FILE"
}

expand_user_path() {
    case "$1" in
        "~") printf '%s\n' "$HOME" ;;
        "~/"*) printf '%s/%s\n' "$HOME" "${1#~/}" ;;
        *) printf '%s\n' "$1" ;;
    esac
}

echo ""
echo -e "  ${BOLD}✦ wispr unleashed${RESET}"
echo ""

if [ "$(uname -s)" != "Darwin" ]; then
    fail "Wispr Unleashed currently supports macOS only"
    exit 1
fi
ok "macOS"

WISPR_DB="$HOME/Library/Application Support/Wispr Flow/flow.sqlite"
if [ ! -f "$WISPR_DB" ]; then
    fail "Wispr Flow not found"
    dim "   install it from https://wispr.com and complete one test recording"
    exit 1
fi
ok "Wispr Flow"

# uv supplies an isolated environment and downloads Python 3.10+ if necessary.
UV_BIN="$(command -v uv 2>/dev/null || true)"
if [ -z "$UV_BIN" ]; then
    echo ""
    dim "installing uv…"
    curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh
    for candidate in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
        if [ -x "$candidate" ]; then
            UV_BIN="$candidate"
            break
        fi
    done
fi

if [ -z "$UV_BIN" ] || [ ! -x "$UV_BIN" ]; then
    fail "uv installation failed"
    dim "   see https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
fi
ok "uv"

echo ""
dim "setting up an isolated Python environment…"
(cd "$ROOT_DIR" && "$UV_BIN" sync --locked --no-dev --quiet)
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
PY_VERSION=$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
ok "Python $PY_VERSION + dependencies"

touch "$ENV_FILE"
chmod 600 "$ENV_FILE"

# Migrate the model identifier written by pre-public-release installers.
if [ "$(get_env "LLM_MODEL")" = "gemini/gemini-3.1-pro" ]; then
    set_env "LLM_MODEL" "gemini/gemini-3.1-pro-preview"
fi

echo ""
if grep -qE '^(OPENAI_API_KEY|ANTHROPIC_API_KEY|GOOGLE_API_KEY|GEMINI_API_KEY)=.+' "$ENV_FILE" 2>/dev/null; then
    MODEL=$(get_env "LLM_MODEL")
    ok "LLM configured${MODEL:+ ($MODEL)}"
else
    echo -e "  ${DIM}note generation — choose your LLM provider${RESET}"
    echo ""
    echo -e "     ${CYAN}1${RESET}  Google Gemini"
    echo -e "     ${CYAN}2${RESET}  OpenAI"
    echo -e "     ${CYAN}3${RESET}  Anthropic"
    echo -e "     ${CYAN}4${RESET}  Skip ${DIM}— configure .env later${RESET}"
    echo ""
    read -rp "  choice [1]: " provider
    provider=${provider:-1}

    case "$provider" in
        1)
            dim "get a key at https://aistudio.google.com/apikey"
            read -srp "  paste your API key: " api_key
            echo ""
            if [ -n "$api_key" ]; then
                set_env "GOOGLE_API_KEY" "$api_key"
                set_env "LLM_MODEL" "gemini/gemini-3.1-pro-preview"
                ok "Gemini configured"
            else
                warn "no key entered"
            fi
            ;;
        2)
            dim "get a key at https://platform.openai.com/api-keys"
            read -srp "  paste your API key: " api_key
            echo ""
            if [ -n "$api_key" ]; then
                set_env "OPENAI_API_KEY" "$api_key"
                set_env "LLM_MODEL" "gpt-4o-mini"
                ok "OpenAI configured"
            else
                warn "no key entered"
            fi
            ;;
        3)
            dim "get a key at https://console.anthropic.com/settings/keys"
            read -srp "  paste your API key: " api_key
            echo ""
            if [ -n "$api_key" ]; then
                set_env "ANTHROPIC_API_KEY" "$api_key"
                set_env "LLM_MODEL" "anthropic/claude-sonnet-5"
                ok "Anthropic configured"
            else
                warn "no key entered"
            fi
            ;;
        *)
            dim "skipped — edit $ENV_FILE when ready"
            ;;
    esac
fi

echo ""
EXISTING_VAULT=$(get_env "OBSIDIAN_VAULT")
if [ -n "$EXISTING_VAULT" ] && [ -d "$(expand_user_path "$EXISTING_VAULT")" ]; then
    ok "Obsidian vault → ${EXISTING_VAULT/$HOME/~}"
else
    echo -e "  ${BOLD}Obsidian vault${RESET}"
    dim "notes and transcripts will be saved here"
    echo ""
    echo -e "     ${CYAN}1${RESET}  Scan my Mac"
    echo -e "     ${CYAN}2${RESET}  Enter path"
    echo -e "     ${CYAN}3${RESET}  Skip"
    echo ""
    read -rp "  choice [1]: " vault_method
    vault_method=${vault_method:-1}
    CHOSEN_VAULT=""

    if [ "$vault_method" = "1" ]; then
        dim "scanning common vault locations…"
        DETECTED_VAULTS=()
        for root in \
            "$HOME/Desktop" \
            "$HOME/Documents" \
            "$HOME/Library/Mobile Documents/iCloud~md~obsidian/Documents"; do
            [ -d "$root" ] || continue
            while IFS= read -r marker; do
                vault="$(dirname "$marker")"
                duplicate=false
                for existing in "${DETECTED_VAULTS[@]}"; do
                    [ "$existing" = "$vault" ] && duplicate=true
                done
                if [ "$duplicate" = false ]; then
                    DETECTED_VAULTS+=("$vault")
                fi
            done < <(find "$root" -maxdepth 4 -name .obsidian -type d 2>/dev/null)
        done

        if [ ${#DETECTED_VAULTS[@]} -gt 0 ]; then
            echo ""
            i=1
            for vault in "${DETECTED_VAULTS[@]}"; do
                echo -e "     ${CYAN}$i${RESET}  ${vault/$HOME/~}"
                i=$((i + 1))
            done
            echo ""
            read -rp "  choice [1]: " vault_choice
            vault_choice=${vault_choice:-1}
            if [ "$vault_choice" -ge 1 ] 2>/dev/null && [ "$vault_choice" -le "${#DETECTED_VAULTS[@]}" ]; then
                CHOSEN_VAULT="${DETECTED_VAULTS[$((vault_choice - 1))]}"
            fi
        else
            warn "no Obsidian vaults found"
            vault_method="2"
        fi
    fi

    if [ "$vault_method" = "2" ]; then
        read -rep "  vault path: " manual_path
        if [ -n "$manual_path" ]; then
            candidate=$(expand_user_path "$manual_path")
            if [ -d "$candidate" ]; then
                CHOSEN_VAULT="$candidate"
            else
                warn "that folder does not exist; open or create the vault in Obsidian first"
            fi
        fi
    fi

    if [ -n "$CHOSEN_VAULT" ]; then
        VAULT_SHORT="${CHOSEN_VAULT/$HOME/~}"
        set_env "OBSIDIAN_VAULT" "$VAULT_SHORT"
        mkdir -p "$CHOSEN_VAULT/Transcripts"
        read -rp "  your first name (optional): " user_name
        [ -n "$user_name" ] && set_env "USER_NAME" "$user_name"
        ok "vault → $VAULT_SHORT"
    elif [ "$vault_method" != "3" ]; then
        warn "vault not configured — set OBSIDIAN_VAULT in .env before recording"
    fi
fi

# Install both a normal executable and a shell function that supersedes the
# function written by older versions of this installer.
BIN_DIR="$HOME/.local/bin"
WISPR_BIN="$BIN_DIR/wispr"
mkdir -p "$BIN_DIR"
{
    echo '#!/bin/sh'
    printf 'exec "%s" "%s/record.py" "$@"\n' "$PYTHON_BIN" "$ROOT_DIR"
} > "$WISPR_BIN"
chmod 755 "$WISPR_BIN"
ok "wispr command → ~/.local/bin/wispr"

SHELL_NAME="$(basename "${SHELL:-zsh}")"
if [ "$SHELL_NAME" = "bash" ]; then
    RC_FILE="$HOME/.bashrc"
else
    RC_FILE="$HOME/.zshrc"
fi

RC_TEMP="$RC_FILE.tmp.$$"
if [ -f "$RC_FILE" ]; then
    awk '
        $0 == "# >>> wispr-unleashed >>>" { skip=1; next }
        $0 == "# <<< wispr-unleashed <<<" { skip=0; next }
        !skip { print }
    ' "$RC_FILE" > "$RC_TEMP"
else
    : > "$RC_TEMP"
fi
{
    echo ""
    echo '# >>> wispr-unleashed >>>'
    echo 'export PATH="$HOME/.local/bin:$PATH"'
    echo 'wispr() {'
    printf '  "%s" "%s/record.py" "$@"\n' "$PYTHON_BIN" "$ROOT_DIR"
    echo '}'
    echo '# <<< wispr-unleashed <<<'
} >> "$RC_TEMP"
mv "$RC_TEMP" "$RC_FILE"

echo ""
echo -e "  ${GREEN}●${RESET} ${BOLD}ready${RESET}"
echo ""
dim "restart Terminal or run: source ${RC_FILE/$HOME/~}"
echo -e "  then start with: ${BOLD}wispr${RESET} ${DIM}\"Meeting Title\"${RESET}"
echo ""
