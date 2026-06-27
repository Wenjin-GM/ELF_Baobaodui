#!/usr/bin/env bash
set -eo pipefail

cd "${1:-$HOME/smart_tool_cabinet/ros2_ws}"
source /opt/ros/humble/setup.bash
source install/setup.bash

pids=()
cleanup() {
  for pid in "${pids[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT

wait_topic_once() {
  local topic="$1"
  local timeout_sec="${2:-8}"
  python3 - "$topic" "$timeout_sec" <<'PY'
import sys
import rclpy
from std_msgs.msg import String

topic = sys.argv[1]
timeout_sec = float(sys.argv[2])
received = []

rclpy.init()
node = rclpy.create_node("real_smoke_topic_waiter")

def callback(msg):
    print(msg)
    received.append(msg.data)

node.create_subscription(String, topic, callback, 10)
deadline = node.get_clock().now().nanoseconds / 1e9 + timeout_sec
while not received and node.get_clock().now().nanoseconds / 1e9 < deadline:
    rclpy.spin_once(node, timeout_sec=0.2)

node.destroy_node()
rclpy.shutdown()
if not received:
    raise SystemExit(f"timeout waiting for {topic}")
PY
}

echo "== real env_node SHT30 =="
ros2 run smart_cabinet_nodes env_node --ros-args -p period_sec:=1.0 > /tmp/real_env.log 2>&1 &
pids+=("$!")
sleep 2
wait_topic_once /env/state 8
kill "${pids[-1]}" 2>/dev/null || true
unset 'pids[-1]'

echo "== real actuator_node safety reject only =="
ros2 run smart_cabinet_nodes actuator_node > /tmp/real_actuator.log 2>&1 &
pids+=("$!")
sleep 2
python3 - <<'PY'
import rclpy
from smart_cabinet_interfaces.srv import OpenLock

rclpy.init()
node = rclpy.create_node("real_lock_reject_client")
client = node.create_client(OpenLock, "/actuator/open_lock")
assert client.wait_for_service(timeout_sec=5.0)
req = OpenLock.Request()
req.pulse_sec = 0.8
future = client.call_async(req)
rclpy.spin_until_future_complete(node, future, timeout_sec=5.0)
print(future.result())
assert future.result() is not None and future.result().success is False
node.destroy_node()
rclpy.shutdown()
PY
kill "${pids[-1]}" 2>/dev/null || true
unset 'pids[-1]'

echo "== real nfc_node timeout smoke =="
ros2 run smart_cabinet_nodes nfc_node > /tmp/real_nfc.log 2>&1 &
pids+=("$!")
sleep 2
python3 - <<'PY'
import rclpy
from rclpy.action import ActionClient
from smart_cabinet_interfaces.action import ReadNfcCard

rclpy.init()
node = rclpy.create_node("real_nfc_timeout_client")
client = ActionClient(node, ReadNfcCard, "/auth/read_nfc_card")
assert client.wait_for_server(timeout_sec=5.0)
goal = ReadNfcCard.Goal()
goal.timeout_sec = 1.0
send = client.send_goal_async(goal)
rclpy.spin_until_future_complete(node, send, timeout_sec=3.0)
goal_handle = send.result()
assert goal_handle and goal_handle.accepted
res_future = goal_handle.get_result_async()
rclpy.spin_until_future_complete(node, res_future, timeout_sec=4.0)
print(res_future.result().result)
node.destroy_node()
rclpy.shutdown()
PY
kill "${pids[-1]}" 2>/dev/null || true
unset 'pids[-1]'

echo "== real smoke logs =="
for file in /tmp/real_env.log /tmp/real_actuator.log /tmp/real_nfc.log; do
  echo "--- $file"
  tail -30 "$file" || true
done

echo "real smoke test complete"
