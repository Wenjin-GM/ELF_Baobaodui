#!/usr/bin/env bash
# B-layer test: face_node dry-run timeout (no mock user → timeout)
set -eo pipefail

cd ~/smart_tool_cabinet/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
export PYTHONDONTWRITEBYTECODE=1

# Kill any leftover face_node action server
pkill -f "smart_cabinet_nodes.*face_node" 2>/dev/null || true
sleep 1

LOG_DIR=~/smart_tool_cabinet/data/ros_logs/face_node_tests/$(date +%Y%m%d_%H%M%S)
mkdir -p "$LOG_DIR"

echo "=== face_node dry-run timeout test ===" | tee "$LOG_DIR/result.txt"
echo "MODE=B_dry_run_timeout" | tee -a "$LOG_DIR/result.txt"

# Start face_node with empty mock_user_name → will timeout
# mock_user_name defaults to "" → goes to timeout path
ros2 run smart_cabinet_nodes face_node \
  --ros-args \
  -p dry_run:=true \
  > "$LOG_DIR/face_node.log" 2>&1 &
FACE_PID=$!

echo "face_node PID=$FACE_PID" | tee -a "$LOG_DIR/result.txt"
sleep 2

# Run scenario_player expecting failure
ros2 run smart_cabinet_nodes scenario_player \
  --ros-args \
  -p mode:=face_action_client \
  -p timeout_sec:=2.0 \
  -p min_confidence:=0.45 \
  -p expect_success:=false \
  -p expect_message:=mock \
  > "$LOG_DIR/scenario_player.log" 2>&1
EXIT_CODE=$?

# Cleanup
kill $FACE_PID 2>/dev/null || true
wait $FACE_PID 2>/dev/null || true

echo "SCENARIO_EXIT=$EXIT_CODE" | tee -a "$LOG_DIR/result.txt"
if [ $EXIT_CODE -eq 0 ]; then
    echo "PASS" | tee -a "$LOG_DIR/result.txt"
else
    echo "FAIL" | tee -a "$LOG_DIR/result.txt"
fi

echo ""
echo "--- scenario_player log ---"
cat "$LOG_DIR/scenario_player.log"

exit $EXIT_CODE
