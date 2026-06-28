#!/usr/bin/env bash
# D-layer test: face_node real dependency initialization.
set -eo pipefail

cd ~/smart_tool_cabinet/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
export PYTHONDONTWRITEBYTECODE=1

pkill -f "smart_cabinet_nodes.*face_node" 2>/dev/null || true
sleep 1

LOG_DIR=~/smart_tool_cabinet/data/ros_logs/face_node_tests/$(date +%Y%m%d_%H%M%S)
mkdir -p "$LOG_DIR"

echo "=== face_node real init test ===" | tee "$LOG_DIR/result.txt"
echo "MODE=D_real_init" | tee -a "$LOG_DIR/result.txt"

ros2 run smart_cabinet_nodes face_node \
  --ros-args \
  -p dry_run:=false \
  -p camera:=/dev/video21 \
  -p face_db:=/home/elf/smart_tool_cabinet/USB/face_auth/face_db \
  > "$LOG_DIR/face_node.log" 2>&1 &
FACE_PID=$!

echo "face_node PID=$FACE_PID" | tee -a "$LOG_DIR/result.txt"
sleep 10

kill $FACE_PID 2>/dev/null || true
wait $FACE_PID 2>/dev/null || true

if grep -q "FaceRecognizer ready" "$LOG_DIR/face_node.log"; then
    echo "PASS" | tee -a "$LOG_DIR/result.txt"
    EXIT_CODE=0
else
    echo "FAIL" | tee -a "$LOG_DIR/result.txt"
    EXIT_CODE=1
fi

echo ""
echo "--- face_node log ---"
cat "$LOG_DIR/face_node.log"

exit $EXIT_CODE
