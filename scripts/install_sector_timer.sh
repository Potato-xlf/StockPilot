#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if [ "$(id -u)" -ne 0 ]; then
    echo "run as root" >&2
    exit 1
fi

install -m 0644 "$SCRIPT_DIR/stockpilot-sectors.service" /etc/systemd/system/
install -m 0644 "$SCRIPT_DIR/stockpilot-sectors.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now stockpilot-sectors.timer
systemctl list-timers stockpilot-sectors.timer --no-pager
