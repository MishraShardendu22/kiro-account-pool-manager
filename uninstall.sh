#!/usr/bin/env bash
set -euo pipefail

TARGET_BIN="$HOME/.local/bin/kiro-pool"
PROFILES_DIR="$HOME/.local/share/kiro-profiles"
KIRO_PROFILES_DIR="$HOME/.kiro-profiles"

echo "==> Uninstalling kiro-pool..."

if [[ -f "$TARGET_BIN" ]]; then
  rm -f "$TARGET_BIN"
  echo "Removed executable: $TARGET_BIN"
else
  echo "Notice: $TARGET_BIN not found."
fi

if [[ "${1:-}" == "--purge" ]]; then
  echo "Purging all profile data and credentials..."
  rm -rf "$PROFILES_DIR" "$KIRO_PROFILES_DIR" /tmp/kiro-run-*-"$(id -u)"
  echo "Cleaned up profile storage."
else
  echo "Profile data was preserved at: $PROFILES_DIR"
  echo "To purge all profile credentials and storage as well, run: ./uninstall.sh --purge"
fi

echo "Done."
