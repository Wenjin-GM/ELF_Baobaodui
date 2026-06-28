#!/usr/bin/env bash
# C-layer test: face_node rejects invalid goal timeout_sec <= 0.
set -eo pipefail

cd ~/smart_tool_cabinet/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
export PYTHONDONTWRITEBYTECODE=1

pkill -f "smart_cabinet_nodes.*face_node" 2>/dev/null || true
sleep 1

LOG_DIR=~/smart_tool_cabinet/data/ros_logs/face_node_tests/$(date +%Y%m%d_%H%M%S)
mkdir -p "$LOG_DIR"

echo "=== face_node invalid-goal reject test ===" | tee "$LOG_DIR/result.txt"
echo "MODE=C_goal_reject" | tee -a "$LOG_DIR/result.txt"

ros2 run smart_cabinet_nodes face_node \
  --ros-args \
  -p dry_run:=true \
  -p mock_user_name:=TestUser \
  > "$LOG_DIR/face_node.log" 2>&1 &
FACE_PID=$!

echo "face_node PID=$FACE_PID" | tee -a "$LOG_DIR/result.txt"
sleep 2

set +e
ros2 run smart_cabinet_nodes scenario_player \
  --ros-args \
  -p mode:=face_action_client \
  -p timeout_sec:=0.0 \
  -p min_confidence:=0.45 \
  -p expect_goal_accepted:=false \
  > "$LOG_DIR/scenario_player.log" 2>&1
EXIT_CODE=$?
set -e

kill $FACE_PID 2>/dev/null || true
wait $FACE_PID 2>/dev/null || true

echo "SCENARIO_EXIT=$EXIT_CODE" | tee -a "$LOG_DIR/result.txt"
if [ $EXIT_CODE -eq 0 ]; then
    echo "PASS" | tee -a "$LOG_DIR/result.txt"
else
    echo "FAIL" | tee -a "$LOG_DIR/result.txt"
fi

echo ""
echo "--- face_node log ---"
cat "$LOG_DIR/face_node.log"
echo ""
echo "--- scenario_player log ---"
cat "$LOG_DIR/scenario_player.log"

exit $EXIT_CODE
