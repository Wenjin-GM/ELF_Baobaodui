#!/usr/bin/env bash

source /opt/ros/humble/setup.bash

echo "== ROS environment =="
echo "ROS_DISTRO=${ROS_DISTRO:-}"
echo "ROS_VERSION=${ROS_VERSION:-}"
echo "ROS_PYTHON_VERSION=${ROS_PYTHON_VERSION:-}"
echo "RMW_IMPLEMENTATION=${RMW_IMPLEMENTATION:-default}"
which ros2

echo
echo "== Python imports =="
python3 - <<'PY'
mods = ["rclpy", "std_msgs.msg", "sensor_msgs.msg", "launch"]
for mod in mods:
    try:
        __import__(mod)
        print(f"{mod}: ok")
    except Exception as exc:
        print(f"{mod}: missing ({exc})")

try:
    import numpy
    print(f"numpy: {numpy.__version__} ({numpy.__file__})")
except Exception as exc:
    print(f"numpy: missing ({exc})")

try:
    from cv_bridge import CvBridge
    bridge = CvBridge()
    print(f"cv_bridge.CvBridge: ok ({bridge.__class__.__name__})")
except Exception as exc:
    print(f"cv_bridge.CvBridge: failed ({exc})")
PY

echo
echo "== Package count and key packages =="
ros2 pkg list > /tmp/ros2_pkgs.txt
wc -l /tmp/ros2_pkgs.txt
for pkg in rclpy std_msgs sensor_msgs cv_bridge image_transport demo_nodes_py launch_ros; do
    if grep -qx "$pkg" /tmp/ros2_pkgs.txt; then
        echo "$pkg: ok"
    else
        echo "$pkg: missing"
    fi
done

echo
echo "== Demo pub/sub test =="
rm -f /tmp/ros2_listener.log /tmp/ros2_talker.log
timeout 8 ros2 run demo_nodes_py listener > /tmp/ros2_listener.log 2>&1 &
listener_pid=$!
sleep 1
timeout 4 ros2 run demo_nodes_py talker > /tmp/ros2_talker.log 2>&1
talker_status=$?
sleep 1
if kill -0 "$listener_pid" 2>/dev/null; then
    kill "$listener_pid" 2>/dev/null || true
fi
wait "$listener_pid" 2>/dev/null || true

echo "-- talker status: $talker_status"
sed -n '1,8p' /tmp/ros2_talker.log
echo "-- listener first messages"
sed -n '1,8p' /tmp/ros2_listener.log

if grep -q "I heard" /tmp/ros2_listener.log; then
    echo "pubsub: ok"
else
    echo "pubsub: failed"
    exit 2
fi

echo
echo "== Hardware permissions =="
id
ls -l /dev/gpiochip3 /dev/i2c-4 /dev/i2c-7 /dev/video11 /dev/video21 2>/dev/null || true
