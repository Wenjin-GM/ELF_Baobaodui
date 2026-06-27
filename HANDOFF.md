# Smart Tool Cabinet Project Handoff

> Last updated: 2026-06-27

This is the core entry document for the BaoBao Team smart safety tool cabinet workspace. A new AI assistant should read this file first, then open the memory files listed below as needed. The board-side source tree should stay synchronized with this local `workspace/` directory at:

```bash
~/smart_tool_cabinet/
```

## 1. Project Overview

The project is an RK3588/ELF 2 based smart safety tool cabinet for power-grid operation and maintenance. The current implementation is moving from standalone module tests toward a ROS2 Humble architecture.

Core functions:

- Identity authentication: PN532 NFC plus face recognition.
- Environment monitoring: SHT30 temperature/humidity over I2C.
- Actuation: fan relay, door lock relay, buzzer.
- Touch UI: PyQt5 display screen with ROS backend.
- Inventory: cabinet camera triggered inventory, not high-frequency streaming. Battery-box and inventory nodes are not complete yet and are currently mocked by `cabinet_logic_node`.
- Runtime data storage: `workspace/data/` contains logs, inventory images, results, events, auth records, environment records, actuator state, and run metadata.

Primary board access:

```bash
ssh elf@10.209.164.14
```

## 2. Workspace Index

Important paths:

- `README.md`: older project overview; useful but not authoritative for newest wiring.
- `HANDOFF.md`: this file, the current project entry point.
- `docs/connect_way.md`: newest wiring and pin mapping. Some text may display garbled on Windows, but the content source is latest hardware mapping.
- `log/6.27.txt`: ROS framework design notes from the user and assistant.
- `PN532/`: PN532 I2C driver and standalone NFC tests.
- `sht30_test/`: SHT30 standalone C test.
- `USB/face_auth/`: USB camera face-auth code based on InsightFace.
- `vision/camera/`: camera probe and capture scripts.
- `show/Script/`: PyQt5 display UI.
- `gpio/`: GPIO hardware test code.
- `ros2_ws/`: ROS2 Humble workspace.
- `start_all_ros_nodes.sh`: starts ROS nodes and foreground monitor.
- `stop_all_ros_nodes.sh`: stops started ROS nodes.
- `data/`: runtime records and ROS logs.
- `.claude/memory/`: structured project memory files.

ROS packages:

- `smart_cabinet_interfaces`: custom services/actions.
- `smart_cabinet_nodes`: Python ROS nodes.

Implemented ROS nodes:

- `env_node`: reads SHT30 and publishes `/env/state`.
- `actuator_node`: controls fan, door lock, buzzer and publishes `/actuator/state`.
- `nfc_node`: exposes `/auth/read_nfc_card` action. Startup must not continuously poll NFC.
- `face_node`: exposes `/auth/authenticate_face` action.
- `cabinet_logic_node`: main system state machine and UI data aggregator.
- `ui_node`: PyQt5/ROS bridge and display launcher.
- `console_monitor`: terminal status monitor used by start script.

Not yet fully implemented:

- `battery_node`.
- Real `vision_node` for cabinet inventory.
- Robust PN532 reset/recovery path.
- Fully working face recognition dependency stack.

## 3. Memory File Index

Open these files for deeper context:

- `.claude/memory/2026-06-27_project-overview.md`: project background, user preferences, synchronization rules.
- `.claude/memory/2026-06-27_hardware-wiring.md`: hardware wiring and verified bus/GPIO mapping.
- `.claude/memory/2026-06-27_ros-architecture.md`: ROS2 node design, topics, services, actions, state machine.
- `.claude/memory/2026-06-27_module-tests.md`: module test commands and observed results.
- `.claude/memory/2026-06-27_pn532-incident.md`: NFC/PN532 incident timeline, current restored state, cautions.
- `.claude/memory/2026-06-27_ui-display.md`: display module, UI node behavior, camera preview status.
- `.claude/memory/2026-06-27_operations-and-ai-rules.md`: AI usage rules, board sync commands, safe test policy.

## 4. Core Knowledge

Hardware mapping currently used:

- SHT30: `SDA.1/SCL.1`, `/dev/i2c-4`, address `0x44`.
- PN532: `SDA.0/SCL.0`, expected `/dev/i2c-7`, address `0x24`.
- Fan relay: `GPIO.28`, Linux `gpiochip3 line 9`, active-low relay, controls fan.
- Door lock relay: `GPIO.25`, Linux `gpiochip3 line 3`, active-low relay, controls door lock. Single pulse must be `<= 0.5s`.
- Buzzer: `GPIO.23`, Linux `gpiochip3 line 4`, active-high. `1` sounds, `0` silent.
- Battery charging module: not connected yet.

Known device observations:

- `i2cdetect -y 4` should show SHT30 at `0x44`.
- `i2cdetect -y 7` should show PN532 at `0x24` when module is healthy.
- PN532 can enter an I2C no-ACK state after failed/no-card experiments. If `0x24` disappears, stop all NFC access and power-cycle the PN532 module.
- `/dev/video11` was previously probed as readable 1920x1080. `/dev/video21` is used by face node by default.

## 5. Completed Work

Project organization:

- Workspace was cleaned and docs moved into `docs/` earlier.
- `workspace` and board path `~/smart_tool_cabinet/` have repeatedly been kept in sync via `scp` and board-side rebuilds.
- `data/` runtime directory structure was created for logs/images/results.

Hardware/function tests:

- PN532 once successfully read a campus card UID (real UID intentionally not stored in Git) with:
  ```bash
  python3 PN532/tests/test_campus_card_uid.py --bus 7 --timeout 30
  ```
- SHT30 standalone test was reported working.
- USB face-auth image check loaded face DB but showed `no_face` for sample captures.
- Camera probe showed `/dev/video11` readable and `/dev/video12` not readable.
- GPIO fan/door-lock test script was created earlier; door lock pulse must stay under `0.5s`.

ROS2:

- ROS2 Humble installed and verified.
- NumPy compatibility and udev permissions were handled earlier.
- `check_ros2_board.sh` passed with `rclpy`, `std_msgs`, `sensor_msgs`, `cv_bridge`, demo pub/sub.
- `start_all_ros_nodes.sh` and `stop_all_ros_nodes.sh` exist.
- `start_all_ros_nodes.sh` runs a foreground monitor and stops nodes on Ctrl+C.
- `cabinet_logic_node` was made the system-level source of truth for authentication state and UI aggregation.
- UI subscribes to `/ui/*` aggregate data instead of raw sensor topics.

## 6. Current Critical Issues

PN532:

- The user requested a full restoration of the NFC module code after experiments with safe AutoPoll/InList paths caused instability.
- `PN532/drivers/i2c_pn532.py` has been restored to the original-style API:
  ```python
  nfc.read_passive_target_id(timeout=1.0)
  ```
  There is no `safe=` parameter and no AutoPoll helper in the current restored file.
- Two temporary scripts were removed:
  - `PN532/tests/test_safe_uid_once.py`
  - `PN532/tests/test_card_present_uid.py`
- Temporary `docs/PN532_SAFE_USE.md` was removed.
- Board still may have a root-owned `PN532/drivers/__pycache__` from previous sudo tests. User was asked to delete it on board:
  ```bash
  cd ~/smart_tool_cabinet
  sudo rm -rf PN532/drivers/__pycache__ PN532/tests/__pycache__
  ```
- After deleting cache and power-cycling PN532, retest the original command:
  ```bash
  cd ~/smart_tool_cabinet/PN532
  python3 tests/test_campus_card_uid.py --bus 7 --timeout 30
  ```

Face recognition:

- `face_node` currently reports:
  ```text
  cannot import name 'docstring' from 'matplotlib'
  ```
- This is likely a Python/matplotlib/InsightFace dependency conflict and is not fixed yet.

UI:

- Auth page camera preview was originally just a placeholder. A partial OpenCV preview edit was attempted in `show/Script/pages/auth_page.py`; verify before relying on it.
- UI fullscreen and Ctrl+C behavior were previously improved in `ui_node`, but display-side behavior should be rechecked on board.

## 7. Main Commands

Board build:

```bash
cd ~/smart_tool_cabinet/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source install/setup.bash
```

Start all current ROS nodes:

```bash
cd ~/smart_tool_cabinet
bash start_all_ros_nodes.sh
```

Stop all nodes:

```bash
cd ~/smart_tool_cabinet
bash stop_all_ros_nodes.sh
```

Run UI on board display:

```bash
cd ~/smart_tool_cabinet/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash
DISPLAY=:0 XAUTHORITY=/run/user/1000/gdm/Xauthority QT_QPA_PLATFORM=xcb ros2 run smart_cabinet_nodes ui_node
```

Check I2C:

```bash
i2cdetect -y 4
i2cdetect -y 7
```

## 8. AI Usage Rules

- Always treat `workspace/` as the canonical local project workspace.
- Keep board source `~/smart_tool_cabinet/` synchronized with local changes that affect execution.
- Before editing, inspect current files. The worktree may contain user changes; do not revert unrelated edits.
- Do not run destructive commands unless explicitly requested.
- Do not use `RPi.GPIO`; RK3588 uses `gpiod` or system GPIO tools.
- For PN532, never run repeated no-card experiments casually. If `0x24` disappears from I2C, stop all NFC processes and ask the user to power-cycle PN532.
- Door lock pulse must never exceed `0.5s`.
- UI should receive business-level data from `cabinet_logic_node`, not raw sensor topics.
- Cabinet inventory camera should be triggered, not high-frequency raw image publishing.
- If using ROS, rebuild on board after source changes and verify install artifacts.

## 9. Immediate Next Steps

1. User should clear PN532 root-owned cache and power-cycle PN532.
2. Re-run original standalone NFC test.
3. If standalone NFC works again, freeze PN532 driver as baseline before any ROS integration.
4. Fix `nfc_node` integration cautiously, preferably after wiring PN532 reset pin to GPIO.
5. Fix face recognition dependency issue.
6. Verify UI auth page preview and full-system authentication state propagation.
7. Implement or mock-safe `battery_node` and real `vision_node`.
