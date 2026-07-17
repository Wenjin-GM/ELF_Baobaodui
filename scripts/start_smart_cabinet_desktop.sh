#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="$PROJECT_ROOT/data"
RUN_DIR="$DATA_DIR/run"
LOG_DIR="$DATA_DIR/desktop_launcher_logs"
mkdir -p "$RUN_DIR" "$LOG_DIR"

exec 9>"$RUN_DIR/desktop_start.lock"
if ! flock -n 9; then
  echo "$(date '+%F %T') smart cabinet start is already in progress" >>"$LOG_DIR/start.log"
  exit 0
fi

BOOT_DELAY="${SMART_CABINET_BOOT_DELAY:-0}"
if [[ "$BOOT_DELAY" != "0" ]]; then
  sleep "$BOOT_DELAY"
fi

export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-/run/user/1000/gdm/Xauthority}"
export SMART_CABINET_PROJECT_ROOT="${SMART_CABINET_PROJECT_ROOT:-$PROJECT_ROOT}"
export SMART_CABINET_START_VISION="${SMART_CABINET_START_VISION:-1}"
export SMART_CABINET_START_NFC="${SMART_CABINET_START_NFC:-1}"
export SMART_CABINET_UI_MODE="${SMART_CABINET_UI_MODE:-fullscreen}"
export SMART_CABINET_FOREGROUND="${SMART_CABINET_FOREGROUND:-0}"

wait_for_display() {
  local i
  for i in $(seq 1 60); do
    if command -v xrandr >/dev/null 2>&1 && xrandr --query >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.5
  done
  return 0
}

ui_running() {
  pgrep -f '/smart_cabinet_nodes/lib/smart_cabinet_nodes/ui_node|ros2 run smart_cabinet_nodes ui_node' >/dev/null 2>&1
}

{
  echo
  echo "===== $(date '+%F %T') start smart cabinet from desktop/autostart ====="
  wait_for_display

  if ui_running; then
    echo "ui_node is already running; keeping current system"
    "$PROJECT_ROOT/scripts/map_touchscreen_to_hdmi.sh" || true
    exit 0
  fi

  SMART_CABINET_TOUCH_MAP_HOLD_SEC=0 "$PROJECT_ROOT/start_all_ros_nodes.sh"
} >>"$LOG_DIR/start.log" 2>&1