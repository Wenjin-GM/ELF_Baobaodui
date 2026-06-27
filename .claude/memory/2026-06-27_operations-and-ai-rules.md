# 2026-06-27 Operations and AI Rules Memory

## Board Access

SSH:

```bash
ssh elf@10.209.164.14
```

Board source:

```bash
~/smart_tool_cabinet/
```

Local workspace:

```text
D:\Desktop\Elf2官方资料\workspace
```

## Synchronization

When code changes locally, sync to board.

Example:

```bash
scp workspace/PN532/drivers/i2c_pn532.py elf@10.209.164.14:/home/elf/smart_tool_cabinet/PN532/drivers/i2c_pn532.py
```

For ROS node changes, rebuild:

```bash
cd ~/smart_tool_cabinet/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select smart_cabinet_nodes
source install/setup.bash
```

## Start and Stop

Start all nodes:

```bash
cd ~/smart_tool_cabinet
bash start_all_ros_nodes.sh
```

Stop all nodes:

```bash
cd ~/smart_tool_cabinet
bash stop_all_ros_nodes.sh
```

Logs:

```bash
~/smart_tool_cabinet/data/ros_logs/YYYYMMDD_HHMMSS/
```

Latest log dir:

```bash
cat ~/smart_tool_cabinet/data/run/latest_log_dir
```

## Safety Rules

PN532:

- Never assume PN532 recovers automatically after disappearing from I2C.
- If `i2cdetect -y 7` does not show `0x24`, stop NFC work and power-cycle the module.
- Avoid new NFC polling experiments until original standalone test works again.
- Remove root-owned pycache if needed:
  ```bash
  cd ~/smart_tool_cabinet
  sudo rm -rf PN532/drivers/__pycache__ PN532/tests/__pycache__
  ```

Door lock:

- Single energizing pulse must be `<= 0.5s`.
- Prefer `0.3s`.
- `actuator_node` must enforce this internally.

GPIO:

- Do not use `RPi.GPIO`.
- Use `gpiod`/`gpioinfo`/`gpioset`.

UI:

- UI should not own business logic.
- UI sends service requests to `cabinet_logic_node` and displays `/ui/*` topics.

Vision:

- No high-frequency raw image publishing for inventory.
- Trigger capture/inference on close-door or immediate-inventory request only.

## Assistant Behavior Rules

- Read `HANDOFF.md` first.
- Then open relevant `.claude/memory/*.md`.
- Inspect files before editing.
- Preserve user changes; do not revert unrelated work.
- Keep local workspace and board source synchronized.
- After ROS changes, verify build and install artifacts on board.
- When working with hardware, describe expected phenomena and avoid unsafe tests.
