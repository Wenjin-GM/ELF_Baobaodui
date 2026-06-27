# Smart Cabinet ROS2 Workspace

This workspace contains the first ROS2 encapsulation for the smart tool cabinet.

Implemented packages:

- `smart_cabinet_interfaces`: custom actions and services.
- `smart_cabinet_nodes`: Python nodes.

Implemented nodes:

- `env_node`: publishes `/env/state` from SHT30.
- `actuator_node`: provides `/actuator/open_lock`, `/actuator/set_fan`, `/actuator/beep` and publishes `/actuator/state`.
- `nfc_node`: provides `/auth/read_nfc_card` action for PN532.
- `face_node`: provides `/auth/authenticate_face` action.
- `cabinet_logic_node`: main logic node; aggregates lower-level topics into `/ui/*` topics and provides `/cabinet/*` services.

Not implemented yet:

- `vision_node`
- `battery_node`
- `ui_node`

Build on the board:

```bash
cd ~/smart_tool_cabinet/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install
source install/setup.bash
```

Dry-run integration test:

```bash
cd ~/smart_tool_cabinet
bash scripts/test_ros2_nodes_dry_run.sh
```

Non-dangerous real hardware smoke test:

```bash
cd ~/smart_tool_cabinet
bash scripts/test_ros2_nodes_real_smoke.sh
```

Safety note:

- `actuator_node` rejects lock pulses longer than `0.5s`.
- The real smoke test does not energize the lock, fan, or buzzer.
