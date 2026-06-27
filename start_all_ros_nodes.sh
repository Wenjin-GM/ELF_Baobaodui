#!/usr/bin/env bash
set -euo pipefail

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

UI_MODE="${SMART_CABINET_UI_MODE:-fullscreen}"      # fullscreen | windowed | bridge | none
ACTUATOR_DRY_RUN="${SMART_CABINET_ACTUATOR_DRY_RUN:-0}"
ENV_DRY_RUN="${SMART_CABINET_ENV_DRY_RUN:-0}"
FACE_DRY_RUN="${SMART_CABINET_FACE_DRY_RUN:-0}"
NFC_DRY_RUN="${SMART_CABINET_NFC_DRY_RUN:-0}"
NFC_MOCK_UID="${SMART_CABINET_NFC_MOCK_UID:-}"
FOREGROUND="${SMART_CABINET_FOREGROUND:-1}"

as_bool() {
  case "${1,,}" in
    1|true|yes|on) echo true ;;
    *) echo false ;;
  esac
}

ACTUATOR_DRY_RUN="$(as_bool "$ACTUATOR_DRY_RUN")"
ENV_DRY_RUN="$(as_bool "$ENV_DRY_RUN")"
FACE_DRY_RUN="$(as_bool "$FACE_DRY_RUN")"
NFC_DRY_RUN="$(as_bool "$NFC_DRY_RUN")"

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
  sleep 0.3
}

cd "$ROS_WS"

start_node env_node ros2 run smart_cabinet_nodes env_node --ros-args -p period_sec:=1.0 -p dry_run:="$ENV_DRY_RUN"
start_node actuator_node ros2 run smart_cabinet_nodes actuator_node --ros-args -p dry_run:="$ACTUATOR_DRY_RUN"
if [[ -n "$NFC_MOCK_UID" ]]; then
  start_node nfc_node ros2 run smart_cabinet_nodes nfc_node --ros-args -p dry_run:="$NFC_DRY_RUN" -p mock_uid:="$NFC_MOCK_UID"
else
  start_node nfc_node ros2 run smart_cabinet_nodes nfc_node --ros-args -p dry_run:="$NFC_DRY_RUN"
fi
start_node face_node ros2 run smart_cabinet_nodes face_node --ros-args -p dry_run:="$FACE_DRY_RUN"
start_node cabinet_logic_node ros2 run smart_cabinet_nodes cabinet_logic_node

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
echo "all requested ROS nodes started"
echo "logs: $LOG_DIR"
echo "stop: $PROJECT_ROOT/stop_all_ros_nodes.sh"

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
