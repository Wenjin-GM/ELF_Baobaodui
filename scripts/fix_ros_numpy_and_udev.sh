#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "Please run as root:"
    echo "  sudo bash scripts/fix_ros_numpy_and_udev.sh"
    exit 1
fi

TARGET_USER="${1:-elf}"
UDEV_RULE="/etc/udev/rules.d/99-smart-tool-cabinet-permissions.rules"

echo "== Fix NumPy for ROS2 Humble cv_bridge =="
echo "Current NumPy:"
python3 - <<'PY' || true
try:
    import numpy
    print(numpy.__version__)
    print(numpy.__file__)
except Exception as exc:
    print(f"numpy import failed: {exc}")
PY

# The board's root pip may be old and does not support --break-system-packages.
# Ubuntu 22.04 + ROS2 Humble cv_bridge is built against NumPy 1.x ABI.
python3 -m pip install --force-reinstall "numpy==1.26.4"

echo
echo "NumPy after reinstall:"
python3 - <<'PY'
import numpy
print(numpy.__version__)
print(numpy.__file__)
PY

echo
echo "== Configure groups =="
getent group i2c >/dev/null || groupadd i2c
getent group gpio >/dev/null || groupadd gpio
getent group video >/dev/null || groupadd video
usermod -aG i2c,gpio,video "$TARGET_USER"
id "$TARGET_USER"

echo
echo "== Configure udev permissions =="
cat > "$UDEV_RULE" <<'EOF'
# Smart tool cabinet hardware permissions for ROS2/Python nodes.
# I2C: PN532 on /dev/i2c-7, SHT30 on /dev/i2c-4
SUBSYSTEM=="i2c-dev", KERNEL=="i2c-[0-9]*", GROUP="i2c", MODE="0660"

# GPIO: fan/lock/buzzer through libgpiod
SUBSYSTEM=="gpio", KERNEL=="gpiochip[0-9]*", GROUP="gpio", MODE="0660"

# Camera nodes are normally root:video 0660; keep this explicit for stability.
SUBSYSTEM=="video4linux", KERNEL=="video[0-9]*", GROUP="video", MODE="0660"
EOF

udevadm control --reload-rules
udevadm trigger --subsystem-match=i2c-dev || true
udevadm trigger --subsystem-match=gpio || true
udevadm trigger --subsystem-match=video4linux || true

echo
echo "== Current device permissions =="
ls -l /dev/gpiochip3 /dev/i2c-4 /dev/i2c-7 /dev/video11 /dev/video21 2>/dev/null || true

echo
echo "== ROS/cv_bridge check =="
if [ -f /opt/ros/humble/setup.bash ]; then
    # shellcheck disable=SC1091
    source /opt/ros/humble/setup.bash
fi
python3 - <<'PY'
import numpy
print(f"numpy={numpy.__version__} ({numpy.__file__})")
from cv_bridge import CvBridge
bridge = CvBridge()
print(f"cv_bridge={bridge.__class__.__name__} ok")
PY

echo
echo "Done."
echo "Important: log out and log back in, or reboot, so $TARGET_USER gets the new i2c/gpio groups."
