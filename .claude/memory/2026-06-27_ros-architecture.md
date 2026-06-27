# 2026-06-27 ROS Architecture Memory

## Current ROS2 Workspace

Path:

```bash
workspace/ros2_ws
~/smart_tool_cabinet/ros2_ws
```

ROS distro: Humble.

Packages:

- `smart_cabinet_interfaces`
- `smart_cabinet_nodes`

## Main Design Principle

High-risk hardware actions use services/actions, not raw topics.

Triggered workloads:

- NFC/face authentication only during auth window.
- Cabinet inventory only after door close or explicit user request.
- UI receives aggregated display-state topics from `cabinet_logic_node`.

## Nodes

`env_node`:

- Reads SHT30.
- Publishes `/env/state`.

`actuator_node`:

- Controls fan, lock, buzzer.
- Provides:
  - `/actuator/open_lock`
  - `/actuator/set_fan`
  - `/actuator/beep`
- Publishes `/actuator/state`.
- Must enforce lock pulse max `0.5s`.

`nfc_node`:

- Provides `/auth/read_nfc_card` action.
- Must not continuously poll at startup.
- Current driver was restored to original-style `read_passive_target_id(timeout=...)`.
- Integration is risky until PN532 reset pin is wired or standalone test is stable again.

`face_node`:

- Provides `/auth/authenticate_face`.
- Currently blocked by InsightFace/matplotlib dependency issue:
  `cannot import name 'docstring' from 'matplotlib'`.

`cabinet_logic_node`:

- Owns system state.
- Receives raw lower-level state.
- Publishes `/ui/*` aggregate topics.
- Provides `/cabinet/*` services.
- Authentication state is system-level, not just UI-level.

`ui_node`:

- Launches PyQt UI or bridge-only mode.
- Calls `/cabinet/request_open`, `/cabinet/request_inventory`, `/cabinet/request_manual_fan`, `/cabinet/request_temp_unlock`.

## State Machine

Important states:

- `STANDBY`
- `AUTH_PENDING`
- `USER_AUTHED`
- `ADMIN_AUTHED`
- `CABINET_OPEN`
- `CHECKING_AFTER_CLOSE`
- `ALARM_ACTIVE`
- `MAINTENANCE`

## Topics

Raw/lower-level:

- `/env/state`
- `/actuator/state`
- `/battery/state`
- `/vision/inventory_result`
- `/vision/inventory_image`

UI aggregate:

- `/ui/summary`
- `/ui/environment`
- `/ui/inventory`
- `/ui/inventory_image`
- `/ui/battery`
- `/ui/auth`
- `/ui/events`

## Services and Actions

Cabinet services:

- `/cabinet/request_open`
- `/cabinet/request_inventory`
- `/cabinet/request_manual_fan`
- `/cabinet/request_temp_unlock`
- `/cabinet/logout`

Actuator services:

- `/actuator/open_lock`
- `/actuator/set_fan`
- `/actuator/beep`

Actions:

- `/auth/read_nfc_card`
- `/auth/authenticate_face`
- `/vision/run_inventory`

## Launch Scripts

Start:

```bash
cd ~/smart_tool_cabinet
bash start_all_ros_nodes.sh
```

Stop:

```bash
cd ~/smart_tool_cabinet
bash stop_all_ros_nodes.sh
```

The start script creates logs under `data/ros_logs/YYYYMMDD_HHMMSS/` and runs a foreground console monitor.
