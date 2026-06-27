# 2026-06-27 UI Display Memory

## Display Module

UI code lives in:

```text
workspace/show/Script/
```

It is a PyQt5 touch-screen UI with pages such as dashboard, auth, tools, charging, environment, records, settings, and debug.

ROS UI node:

```text
workspace/ros2_ws/src/smart_cabinet_nodes/smart_cabinet_nodes/ui_node.py
```

## ROS Backend

`show/Script/ros_backend.py` adapts ROS topics/services to Qt signals.

Important rule:

- UI should use `/ui/*` aggregate topics from `cabinet_logic_node`.
- UI should not directly implement raw sensor or actuator business logic.

## Known UI Work

Earlier issues:

- Fullscreen did not behave as expected.
- Ctrl+C from SSH did not exit PyQt cleanly.

Work done:

- `ui_node` has signal handling and timer to let Ctrl+C be processed.
- `ui_node` supports:
  - normal fullscreen mode
  - `--windowed`
  - `--bridge-only`

Run on board display:

```bash
cd ~/smart_tool_cabinet/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
DISPLAY=:0 XAUTHORITY=/run/user/1000/gdm/Xauthority QT_QPA_PLATFORM=xcb ros2 run smart_cabinet_nodes ui_node
```

## Auth Page Preview

The auth page originally had only a placeholder text for camera preview.

An OpenCV/QTimer preview edit was attempted in:

```text
show/Script/pages/auth_page.py
```

Default preview device in that attempt:

```text
/dev/video11
```

Face node default device:

```text
/dev/video21
```

Status:

- Treat camera preview as needing verification.
- The file has historical encoding/garbled Chinese issues; be careful when patching.

## Current UI Integration Status

`cabinet_logic_node` publishes `/ui/summary`, `/ui/environment`, `/ui/inventory`, `/ui/battery`, `/ui/auth`, `/ui/events`.

Authentication state propagation was fixed conceptually:

- Authentication should become system state (`USER_AUTHED` or `ADMIN_AUTHED`).
- UI should reflect current user and authorization from `/ui/summary` and `/ui/auth`.

However, full system auth depends on NFC/face reliability and remains blocked.
