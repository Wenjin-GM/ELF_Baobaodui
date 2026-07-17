#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
if [[ -z "$DESKTOP_DIR" ]]; then
  DESKTOP_DIR="$HOME/Desktop"
fi
AUTOSTART_DIR="$HOME/.config/autostart"
USER_SYSTEMD_DIR="$HOME/.config/systemd/user"

mkdir -p "$DESKTOP_DIR" "$AUTOSTART_DIR" "$USER_SYSTEMD_DIR"
chmod +x \
  "$PROJECT_ROOT/start_all_ros_nodes.sh" \
  "$PROJECT_ROOT/stop_all_ros_nodes.sh" \
  "$PROJECT_ROOT/scripts/start_smart_cabinet_desktop.sh" \
  "$PROJECT_ROOT/scripts/stop_smart_cabinet_desktop.sh" \
  "$PROJECT_ROOT/scripts/map_touchscreen_to_hdmi.sh"

cat >"$DESKTOP_DIR/启动智能工具柜.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=启动智能工具柜
Comment=启动智能工具柜整套 ROS 节点和全屏 UI
Exec=$PROJECT_ROOT/scripts/start_smart_cabinet_desktop.sh
Icon=system-run
Terminal=false
StartupNotify=false
Categories=Utility;
EOF

rm -f "$DESKTOP_DIR/停止智能工具柜.desktop"

cat >"$AUTOSTART_DIR/smart-cabinet-system.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Smart Cabinet System Autostart
Comment=开机进入桌面后自动启动智能工具柜系统
Exec=env SMART_CABINET_BOOT_DELAY=12 $PROJECT_ROOT/scripts/start_smart_cabinet_desktop.sh
X-GNOME-Autostart-enabled=true
Terminal=false
StartupNotify=false
EOF

# Do not launch the cabinet through systemd --user: oneshot services can
# clean up child ROS processes after ExecStart exits. Keep GNOME autostart
# as the owner of the desktop UI startup.
if command -v systemctl >/dev/null 2>&1; then
  systemctl --user disable --now smart-cabinet-system.service 2>/dev/null || true
  systemctl --user daemon-reload 2>/dev/null || true
fi
rm -f "$USER_SYSTEMD_DIR/smart-cabinet-system.service"

chmod +x \
  "$DESKTOP_DIR/启动智能工具柜.desktop" \
  "$AUTOSTART_DIR/smart-cabinet-system.desktop"

if command -v gio >/dev/null 2>&1; then
  gio set "$DESKTOP_DIR/启动智能工具柜.desktop" metadata::trusted true 2>/dev/null || true
fi

echo "desktop launcher installed:"
echo "  $DESKTOP_DIR/启动智能工具柜.desktop"
echo "autostart installed:"
echo "  $AUTOSTART_DIR/smart-cabinet-system.desktop"
echo "systemd user autostart disabled for ROS process safety."
echo "stop entry is available inside the dashboard UI."