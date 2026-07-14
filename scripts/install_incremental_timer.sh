#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "run as root" >&2
  exit 1
fi

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
install -m 0644 "${script_dir}/stockpilot-incremental.service" /etc/systemd/system/
install -m 0644 "${script_dir}/stockpilot-incremental.timer" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now stockpilot-incremental.timer
systemctl list-timers stockpilot-incremental.timer --no-pager
