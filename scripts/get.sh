#!/bin/bash
# Remote installer — downloads or safely updates Wispr Unleashed.
# Usage: curl -fsSL https://raw.githubusercontent.com/yashsmehta/wispr-unleashed/main/scripts/get.sh | bash

set -eo pipefail

INSTALL_DIR="$HOME/wispr-unleashed"
REPO_ZIP="https://github.com/yashsmehta/wispr-unleashed/archive/refs/heads/main.zip"
TEMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/wispr-unleashed.XXXXXX")
ARCHIVE="$TEMP_DIR/wispr-unleashed.zip"
NEW_DIR="$TEMP_DIR/wispr-unleashed-main"
BACKUP_DIR="$HOME/.wispr-unleashed-backup-$$"

cleanup() {
    rm -rf "$TEMP_DIR"
}
trap cleanup EXIT INT TERM

echo ""
echo "  ✦ Downloading Wispr Unleashed…"
echo ""

curl -fsSL "$REPO_ZIP" -o "$ARCHIVE"
unzip -qo "$ARCHIVE" -d "$TEMP_DIR"

if [ ! -f "$NEW_DIR/scripts/install.sh" ]; then
    echo "  ✗ Download did not contain a valid Wispr Unleashed installation"
    exit 1
fi

if [ -d "$INSTALL_DIR" ]; then
    # Configuration and prompt templates belong to the user, so carry them
    # forward instead of deleting them during an update.
    [ -f "$INSTALL_DIR/.env" ] && cp "$INSTALL_DIR/.env" "$NEW_DIR/.env"
    if [ -d "$INSTALL_DIR/prompts" ]; then
        cp "$INSTALL_DIR/prompts/"*.md "$NEW_DIR/prompts/" 2>/dev/null || true
    fi
    [ -f "$INSTALL_DIR/obsidian-reference.md" ] && \
        cp "$INSTALL_DIR/obsidian-reference.md" "$NEW_DIR/obsidian-reference.md"

    rm -rf "$BACKUP_DIR"
    mv "$INSTALL_DIR" "$BACKUP_DIR"
fi

if ! mv "$NEW_DIR" "$INSTALL_DIR"; then
    [ -d "$BACKUP_DIR" ] && mv "$BACKUP_DIR" "$INSTALL_DIR"
    echo "  ✗ Could not install Wispr Unleashed"
    exit 1
fi

echo "  ✓ Downloaded to $INSTALL_DIR"

set +e
if [ -t 0 ]; then
    bash "$INSTALL_DIR/scripts/install.sh"
    install_status=$?
elif exec 3</dev/tty 2>/dev/null; then
    # `curl ... | bash` consumes stdin, so interactive answers must come from
    # the controlling terminal rather than the exhausted download pipe.
    bash "$INSTALL_DIR/scripts/install.sh" <&3
    install_status=$?
    exec 3<&-
else
    # Useful for non-interactive test harnesses that explicitly provide input.
    bash "$INSTALL_DIR/scripts/install.sh"
    install_status=$?
fi
set -e

if [ "$install_status" -eq 0 ]; then
    rm -rf "$BACKUP_DIR"
else
    echo ""
    echo "  ⚠ Setup did not finish. Your previous installation is preserved at:"
    echo "    $BACKUP_DIR"
    exit 1
fi
