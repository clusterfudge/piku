#!/bin/sh
# piku-code installer
# Usage: curl -sL https://raw.githubusercontent.com/OWNER/piku-code/main/install.sh | sh
set -e

REPO_URL="https://github.com/OWNER/piku-code"
PIKU_ROOT="${PIKU_ROOT:-$HOME/.piku}"
PLUGIN_DIR="$PIKU_ROOT/plugins/piku_code"
CODE_CLI="$HOME/bin/code"

echo "-----> Installing piku-code plugin..."

# Create directories
mkdir -p "$PIKU_ROOT/plugins" "$HOME/bin"

# Install or update plugin
if [ -d "$PLUGIN_DIR" ]; then
    echo "       Updating existing installation..."
    git -C "$PLUGIN_DIR" pull --quiet
else
    echo "       Cloning plugin..."
    git clone --quiet --depth 1 "$REPO_URL" "$PLUGIN_DIR"
fi

# Install VS Code CLI if missing
if [ -x "$CODE_CLI" ]; then
    echo "       VS Code CLI already installed"
else
    echo "       Installing VS Code CLI..."
    ARCH=$(uname -m)
    case "$ARCH" in
        x86_64)  OS_ARCH="x64" ;;
        aarch64) OS_ARCH="arm64" ;;
        armv7l)  OS_ARCH="armhf" ;;
        *)
            echo "       Unsupported architecture: $ARCH"
            exit 1
            ;;
    esac

    DOWNLOAD_URL="https://code.visualstudio.com/sha/download?build=stable&os=cli-linux-$OS_ARCH"
    curl -sL "$DOWNLOAD_URL" | tar -xz -C "$HOME/bin"
    chmod +x "$CODE_CLI"
    echo "       VS Code CLI installed to $CODE_CLI"
fi

echo "-----> piku-code installed successfully!"
echo ""
echo "       Server-side setup complete."
echo "       To use, update your local 'piku' client script (see README)."
echo ""
