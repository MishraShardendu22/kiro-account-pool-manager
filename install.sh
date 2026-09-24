#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_SRC="$SCRIPT_DIR/bin/kiro-pool"
TARGET_DIR="$HOME/.local/bin"
TARGET_BIN="$TARGET_DIR/kiro-pool"

echo "==> Installing kiro-pool..."

mkdir -p "$TARGET_DIR"
cp "$BIN_SRC" "$TARGET_BIN"
chmod +x "$TARGET_BIN"

echo "Successfully installed kiro-pool to: $TARGET_BIN"

# Check if ~/.local/bin is in PATH
if [[ ":$PATH:" != *":$TARGET_DIR:"* ]]; then
  echo ""
  echo "Notice: $TARGET_DIR is not in your current PATH."
  echo "Add it by adding this line to your ~/.bashrc or ~/.zshrc:"
  echo '  export PATH="$HOME/.local/bin:$PATH"'
fi

echo ""
echo "Try running:"
echo "  kiro-pool status"
echo "  kiro-pool --help"
