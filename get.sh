#!/bin/bash
# Remote installer — curl this script to download and set up Wispr Unleashed.
# Usage: curl -fsSL https://raw.githubusercontent.com/yashsmehta/wispr-unleashed/main/get.sh | bash

set -e

INSTALL_DIR="$HOME/wispr-unleashed"
REPO_ZIP="https://github.com/yashsmehta/wispr-unleashed/archive/refs/heads/main.zip"

echo ""
echo "  ✦ Downloading Wispr Unleashed..."
echo ""

# Download and extract
TMP_ZIP=$(mktemp /tmp/wispr-unleashed-XXXXXX.zip)
curl -fsSL "$REPO_ZIP" -o "$TMP_ZIP"

# Remove old install if present
rm -rf "$INSTALL_DIR"

# Extract to home directory
unzip -qo "$TMP_ZIP" -d /tmp
mv /tmp/wispr-unleashed-main "$INSTALL_DIR"
rm -f "$TMP_ZIP"

echo "  ✓ Downloaded to $INSTALL_DIR"

# Run the installer
cd "$INSTALL_DIR"
bash install.sh
