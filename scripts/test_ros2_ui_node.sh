#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../ros2_ws"
set +u
source /opt/ros/humble/setup.bash
source install/setup.bash
set -u

logic_log="${TMPDIR:-/tmp}/cabinet_logic_ui_test.log"
rm -f "$logic_log"

cleanup() {
  pkill -f '/smart_cabinet_nodes/lib/smart_cabinet_nodes/cabinet_logic_node' 2>/dev/null || true
  pkill -f 'ros2 run smart_cabinet_nodes cabinet_logic_node' 2>/dev/null || true
}
trap cleanup EXIT

cleanup
ros2 run smart_cabinet_nodes cabinet_logic_node >"$logic_log" 2>&1 &
logic_pid=$!
sleep 2

ros2 run smart_cabinet_nodes ui_node --test --request-inventory --test-timeout-sec 5

echo "== cabinet_logic_node log =="
tail -n 80 "$logic_log" || true

kill "$logic_pid" 2>/dev/null || true
wait "$logic_pid" 2>/dev/null || true
