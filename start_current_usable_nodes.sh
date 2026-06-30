#!/usr/bin/env bash
set -euo pipefail

# Start the currently usable real nodes for hands-on cabinet validation.
# Real: SHT30 env, GPIO actuator, PN532 NFC, face preview/auth, cabinet logic, PyQt UI.
# Mocked inside cabinet_logic_node: battery box and cabinet inventory vision.

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROS_WS="$PROJECT_ROOT/ros2_ws"
DATA_DIR="$PROJECT_ROOT/data"
PID_DIR="$DATA_DIR/run"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG_DIR="$DATA_DIR/ros_logs/$STAMP"

mkdir -p \
  "$DATA_DIR/inventory_images" \
  "$DATA_DIR/inventory_result" \
  "$DATA_DIR/ros_logs" \
  "$DATA_DIR/events" \
  "$DATA_DIR/auth" \
  "$DATA_DIR/environment" \
  "$DATA_DIR/battery" \
  "$DATA_DIR/actuator" \
  "$DATA_DIR/ui" \
  "$PID_DIR" \
  "$LOG_DIR"

set +u
source /opt/ros/humble/setup.bash
source "$ROS_WS/install/setup.bash"
set -u

export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-/run/user/1000/gdm/Xauthority}"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
export SMART_CABINET_SHOW_DIR="${SMART_CABINET_SHOW_DIR:-$PROJECT_ROOT/show/Script}"
export PYTHONDONTWRITEBYTECODE=1

UI_MODE="${SMART_CABINET_UI_MODE:-fullscreen}"  # fullscreen | windowed | bridge | none
FOREGROUND="${SMART_CABINET_FOREGROUND:-1}"

start_node() {
  local name="$1"
  shift
  local pid_file="$PID_DIR/${name}.pid"

  if [[ -s "$pid_file" ]]; then
    local old_pid
    old_pid="$(cat "$pid_file")"
    if kill -0 "$old_pid" 2>/dev/null; then
      echo "$name already running: pid=$old_pid"
      return
    fi
  fi

  echo "starting $name"
  setsid nohup "$@" >"$LOG_DIR/${name}.log" 2>&1 &
  echo "$!" >"$pid_file"
  sleep 0.4
}

echo "stopping previous smart cabinet nodes..."
"$PROJECT_ROOT/stop_all_ros_nodes.sh" >/dev/null 2>&1 || true

cd "$ROS_WS"

start_node env_node \
  ros2 run smart_cabinet_nodes env_node \
  --ros-args -p period_sec:=1.0 -p dry_run:=false

start_node actuator_node \
  ros2 run smart_cabinet_nodes actuator_node \
  --ros-args -p dry_run:=false

start_node nfc_node \
  ros2 run smart_cabinet_nodes nfc_node \
  --ros-args -p dry_run:=false -p bus:=7 -p address:=36 -p poll_sec:=0.1

start_node face_node \
  ros2 run smart_cabinet_nodes face_node \
  --ros-args -p dry_run:=false -p camera:=/dev/video21

start_node cabinet_logic_node \
  ros2 run smart_cabinet_nodes cabinet_logic_node

case "$UI_MODE" in
  fullscreen)
    start_node ui_node ros2 run smart_cabinet_nodes ui_node
    ;;
  windowed)
    start_node ui_node ros2 run smart_cabinet_nodes ui_node --windowed
    ;;
  bridge)
    start_node ui_node ros2 run smart_cabinet_nodes ui_node --bridge-only
    ;;
  none)
    echo "ui_node skipped by SMART_CABINET_UI_MODE=none"
    ;;
  *)
    echo "unknown SMART_CABINET_UI_MODE=$UI_MODE" >&2
    exit 2
    ;;
esac

echo "$LOG_DIR" >"$PID_DIR/latest_log_dir"
echo
echo "current usable smart cabinet nodes started"
echo "logs: $LOG_DIR"
echo "stop: $PROJECT_ROOT/stop_all_ros_nodes.sh"
echo
echo "Quick checks:"
echo "  ros2 topic echo /ui/summary --once"
echo "  ros2 topic info /face/preview"
echo "  ros2 action list | grep read_nfc_card"
echo
echo "NFC cards:"
echo "  19C78529 -> User / user"
echo "  2A86BE5B -> admin / admin"
echo
echo "Note: cabinet_logic_node currently gives NFC about 2 seconds before falling back to face."
echo "      After tapping '申请开柜', place the NFC card promptly."

if [[ "$FOREGROUND" != "0" ]]; then
  echo "entering foreground monitor; press Ctrl+C to stop all nodes"
  CLEANED_UP=0
  cleanup() {
    if [[ "$CLEANED_UP" == "1" ]]; then
      return
    fi
    CLEANED_UP=1
    echo
    echo "stopping all ROS nodes..."
    "$PROJECT_ROOT/stop_all_ros_nodes.sh"
  }
  trap cleanup EXIT INT TERM
  ros2 run smart_cabinet_nodes console_monitor
fi
