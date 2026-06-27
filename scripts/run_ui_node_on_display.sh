#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../ros2_ws"

set +u
source /opt/ros/humble/setup.bash
source install/setup.bash
set -u

export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-/run/user/1000/gdm/Xauthority}"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
export SMART_CABINET_SHOW_DIR="${SMART_CABINET_SHOW_DIR:-$HOME/smart_tool_cabinet/show/Script}"

echo "DISPLAY=$DISPLAY"
echo "XAUTHORITY=$XAUTHORITY"
echo "QT_QPA_PLATFORM=$QT_QPA_PLATFORM"
echo "ui_node defaults to fullscreen; pass --windowed for debugging."

exec ros2 run smart_cabinet_nodes ui_node "$@"
