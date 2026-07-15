#!/usr/bin/env bash
set -euo pipefail

# Start the currently usable real nodes for hands-on cabinet validation.
# Real: SHT30 env, PN532 NFC, GPIO actuator, face preview/auth, STM32 PB0/PB1 battery, cabinet logic, PyQt UI.
# Cabinet inventory vision is enabled by default after zones.json calibration.
# Current wiring: SHT30 on i2c-4, PN532 on i2c-7 addr 0x24.

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
export SMART_CABINET_SHOW_DIR="${SMART_CABINET_SHOW_DIR:-$PROJECT_ROOT/show/New-7.3/Script}"
export SMART_CABINET_UI_SCREEN="${SMART_CABINET_UI_SCREEN:-HDMI}"
export PYTHONDONTWRITEBYTECODE=1

UI_MODE="${SMART_CABINET_UI_MODE:-fullscreen}"  # fullscreen | windowed | bridge | none
START_NFC="${SMART_CABINET_START_NFC:-1}"
START_VISION="${SMART_CABINET_START_VISION:-1}"
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

# env_node reads SHT30 on i2c-4. PN532 is on i2c-7, so both can run together.
bash "$PROJECT_ROOT/scripts/i2c4_exclusive_node_ctl.sh" env

start_node actuator_node \
  ros2 run smart_cabinet_nodes actuator_node \
  --ros-args -p dry_run:=false

# battery_node reads STM32 PB0/PB1 gated four-bit presence.
start_node battery_node \
  ros2 run smart_cabinet_nodes battery_node \
  --ros-args \
  -p protocol:=gated \
  -p data_chip:=gpiochip3 \
  -p data_line:=7 \
  -p frame_chip:=gpiochip3 \
  -p frame_line:=1 \
  -p confirm_frames:=2 \
  -p timeout_sec:=8.0 \
  -p period_sec:=3.0

if [[ "$START_NFC" == "1" || "$START_NFC" == "true" || "$START_NFC" == "yes" || "$START_NFC" == "on" ]]; then
  start_node nfc_node \
    ros2 run smart_cabinet_nodes nfc_node \
    --ros-args \
    -p dry_run:=false \
    -p bus:=7 \
    -p address:=36 \
    -p poll_sec:=0.1 \
    -p open_retries:=3
fi

start_node face_node \
  ros2 run smart_cabinet_nodes face_node \
  --ros-args -p dry_run:=false -p camera:=/dev/video21

if [[ "$START_VISION" == "1" || "$START_VISION" == "true" || "$START_VISION" == "yes" || "$START_VISION" == "on" ]]; then
  start_node vision_node \
    ros2 run smart_cabinet_nodes vision_node \
    --ros-args \
    -p dry_run:=false \
    -p device:=/dev/video11 \
    -p model:="$PROJECT_ROOT/vision/inventory/best_stable_20mb.pt" \
    -p zones:="$PROJECT_ROOT/vision/inventory/zones.json"
  SIMULATE_MISSING_VISION=false
else
  SIMULATE_MISSING_VISION=true
fi

start_node cabinet_logic_node \
  ros2 run smart_cabinet_nodes cabinet_logic_node \
  --ros-args \
  -p simulate_missing_battery:=false \
  -p simulate_missing_vision:="$SIMULATE_MISSING_VISION" \
  -p exclusive_i2c4_auth_mode:=false \
  -p nfc_server_wait_sec:=1.0

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
echo "battery_node is started by default (STM32 PB0/PB1 gated: DATA gpiochip3 line 7, FRAME_ACTIVE gpiochip3 line 1)."
echo "nfc_node is started by default (PN532 via i2c-7 addr 0x24)."
echo "SHT30 uses i2c-4."
echo "vision_node is started by default (set SMART_CABINET_START_VISION=0 only when the cabinet camera is unavailable)."
echo
echo "NFC cards:"
echo "  19C78529 -> User / user"
echo "  2A86BE5B -> admin / admin"

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
