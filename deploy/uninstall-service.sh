#!/usr/bin/env bash
# Remove the systemd user service installed by install-service.sh.
set -euo pipefail

UNIT_NAME="fih-bot.service"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

systemctl --user disable --now "$UNIT_NAME" 2>/dev/null || true
rm -f "$UNIT_DIR/$UNIT_NAME"
systemctl --user daemon-reload
echo "Removed $UNIT_DIR/$UNIT_NAME"
