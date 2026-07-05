#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/smart_tool_cabinet}"
ROS_WS="$PROJECT_ROOT/ros2_ws"
LOG_PATH="${LOG_PATH:-/tmp/vision_node_test.log}"
RESULT_PATH="${RESULT_PATH:-/tmp/vision_action_result.txt}"
PID_PATH="${PID_PATH:-/tmp/vision_node_test.pid}"

cd "$ROS_WS"
set +u
source /opt/ros/humble/setup.bash
source install/setup.bash
set -u

pkill -f "smart_cabinet_nodes.vision_node|ros2 run smart_cabinet_nodes vision_node" 2>/dev/null || true

nohup ros2 run smart_cabinet_nodes vision_node \
  --ros-args \
  -p device:=/dev/video11 \
  -p model:="$PROJECT_ROOT/vision/best.pt" \
  -p zones:="$PROJECT_ROOT/vision/inventory/zones.json" \
  >"$LOG_PATH" 2>&1 &
echo "$!" >"$PID_PATH"

cleanup() {
  kill "$(cat "$PID_PATH")" 2>/dev/null || true
}
trap cleanup EXIT

sleep 5
ros2 action list | grep /vision/run_inventory
ros2 action send_goal /vision/run_inventory \
  smart_cabinet_interfaces/action/RunInventory \
  "{reason: ros_test, save_image: true}" \
  >"$RESULT_PATH" 2>&1

cat "$RESULT_PATH"
echo "--- vision log tail ---"
tail -80 "$LOG_PATH"
