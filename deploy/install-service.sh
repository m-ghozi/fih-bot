#!/usr/bin/env bash
# Install the bot as a systemd user service.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_NAME="fih-bot.service"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
PYTHON="$ROOT/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
  echo "error: $PYTHON not found." >&2
  echo "Create the virtualenv and install requirements first (see README)." >&2
  exit 1
fi

if [[ ! -f "$ROOT/.env" ]]; then
  echo "warning: $ROOT/.env not found; the bot will exit without DISCORD_TOKEN." >&2
fi

mkdir -p "$UNIT_DIR"
sed "s|@ROOT@|$ROOT|g" "$ROOT/deploy/fih-bot.service.in" > "$UNIT_DIR/$UNIT_NAME"

systemctl --user daemon-reload
systemctl --user enable --now "$UNIT_NAME"

# Make the user service start after boot, even without logging in.
if command -v loginctl >/dev/null 2>&1; then
  if ! loginctl show-user "$USER" --property=Linger 2>/dev/null | grep -q 'Linger=yes'; then
    loginctl enable-linger "$USER" 2>/dev/null \
      || echo "Note: run 'sudo loginctl enable-linger $USER' to start the bot at boot."
  fi
fi

echo
echo "Installed $UNIT_DIR/$UNIT_NAME"
echo "Status:  systemctl --user status $UNIT_NAME"
echo "Logs:    journalctl --user -u $UNIT_NAME -f"
systemctl --user --no-pager status "$UNIT_NAME" || true
