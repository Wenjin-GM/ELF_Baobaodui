#!/usr/bin/env bash
set -eo pipefail

cd "${1:-$HOME/smart_tool_cabinet/ros2_ws}"
source /opt/ros/humble/setup.bash
source install/setup.bash

LOG_DIR=/tmp/smart_cabinet_ros_test
rm -rf "$LOG_DIR"
mkdir -p "$LOG_DIR"

wait_topic_once() {
  local topic="$1"
  local timeout_sec="${2:-8}"
  python3 - "$topic" "$timeout_sec" <<'PY'
import sys
import rclpy
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String

topic = sys.argv[1]
timeout_sec = float(sys.argv[2])
received = []

rclpy.init()
node = rclpy.create_node("dry_run_topic_waiter")
qos = QoSProfile(
    history=HistoryPolicy.KEEP_LAST,
    depth=10,
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
)

def callback(msg):
    print(msg)
    received.append(msg.data)

sub = node.create_subscription(String, topic, callback, qos)
deadline = node.get_clock().now().nanoseconds / 1e9 + timeout_sec
while not received and node.get_clock().now().nanoseconds / 1e9 < deadline:
    rclpy.spin_once(node, timeout_sec=0.2)

node.destroy_node()
rclpy.shutdown()
if not received:
    raise SystemExit(f"timeout waiting for {topic}")
PY
}

pids=()
cleanup() {
  for pid in "${pids[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT

ros2 run smart_cabinet_nodes actuator_node --ros-args -p dry_run:=true > "$LOG_DIR/actuator.log" 2>&1 &
pids+=("$!")
ros2 run smart_cabinet_nodes env_node --ros-args -p dry_run:=true -p period_sec:=0.5 > "$LOG_DIR/env.log" 2>&1 &
pids+=("$!")
ros2 run smart_cabinet_nodes nfc_node --ros-args -p dry_run:=true > "$LOG_DIR/nfc.log" 2>&1 &
pids+=("$!")
ros2 run smart_cabinet_nodes face_node --ros-args -p dry_run:=true -p mock_user_name:=TestUser -p mock_role:=admin > "$LOG_DIR/face.log" 2>&1 &
pids+=("$!")
ros2 run smart_cabinet_nodes cabinet_logic_node --ros-args -p auth_timeout_sec:=2.0 > "$LOG_DIR/logic.log" 2>&1 &
pids+=("$!")

sleep 4

echo "== node list =="
ros2 node list | sort

echo "== service list =="
ros2 service list | grep -E '/actuator|/cabinet' | sort

echo "== action list =="
ros2 action list | grep -E '/auth|/vision' | sort || true

echo "== /ui/environment sample =="
wait_topic_once /ui/environment 8

echo "== fan service =="
python3 - <<'PY'
import rclpy
from smart_cabinet_interfaces.srv import RequestManualFan

rclpy.init()
node = rclpy.create_node("dry_run_fan_client")
client = node.create_client(RequestManualFan, "/cabinet/request_manual_fan")
assert client.wait_for_service(timeout_sec=5.0)
req = RequestManualFan.Request()
req.on = True
req.reason = "dry_run_test"
future = client.call_async(req)
rclpy.spin_until_future_complete(node, future, timeout_sec=5.0)
print(future.result())
node.destroy_node()
rclpy.shutdown()
PY
sleep 1
wait_topic_once /ui/environment 8

echo "== request open service =="
python3 - <<'PY'
import rclpy
from smart_cabinet_interfaces.srv import RequestOpen

rclpy.init()
node = rclpy.create_node("dry_run_open_client")
client = node.create_client(RequestOpen, "/cabinet/request_open")
assert client.wait_for_service(timeout_sec=5.0)
req = RequestOpen.Request()
req.timeout_sec = 2.0
future = client.call_async(req)
rclpy.spin_until_future_complete(node, future, timeout_sec=5.0)
print(future.result())
node.destroy_node()
rclpy.shutdown()
PY
sleep 5

echo "== /cabinet/state sample after auth/open =="
wait_topic_once /cabinet/state 8

echo "== logic log auth/open proof =="
if ! grep -q "CABINET_OPEN" "$LOG_DIR/logic.log"; then
  echo "cabinet logic did not reach CABINET_OPEN"
  cat "$LOG_DIR/logic.log"
  exit 2
fi
tail -20 "$LOG_DIR/logic.log"

echo "== lock pulse limit direct actuator negative test =="
python3 - <<'PY'
import rclpy
from smart_cabinet_interfaces.srv import OpenLock

rclpy.init()
node = rclpy.create_node("dry_run_lock_client")
client = node.create_client(OpenLock, "/actuator/open_lock")
assert client.wait_for_service(timeout_sec=5.0)
req = OpenLock.Request()
req.pulse_sec = 0.8
future = client.call_async(req)
rclpy.spin_until_future_complete(node, future, timeout_sec=5.0)
print(future.result())
if future.result() is None or future.result().success:
    raise SystemExit("expected overlong lock pulse to be rejected")
node.destroy_node()
rclpy.shutdown()
PY

echo "== logs =="
for file in "$LOG_DIR"/*.log; do
  echo "--- $file"
  tail -20 "$file" || true
done

echo "dry_run test complete"
