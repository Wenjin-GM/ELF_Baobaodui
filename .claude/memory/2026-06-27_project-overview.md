# 2026-06-27 Project Overview Memory

## Project

BaoBao Team smart safety tool cabinet, based on Forlinx ELF 2 / RK3588, for power-grid operation and maintenance.

The system is intended to run locally on the RK3588 board with:

- NFC and face identity authentication.
- Tool cabinet open/close control.
- Environment monitoring and fan control.
- Cabinet inventory and abnormal-item alarm.
- Touch-screen UI.
- Local data logging.

## User Preferences

- User speaks Chinese and expects direct hands-on engineering help.
- User wants `workspace/` to be the main local project workspace.
- Board-side code at `~/smart_tool_cabinet/` must stay synchronized with `workspace/`.
- User values clear command instructions and expected hardware phenomena.
- User expects cautious handling of real hardware, especially door lock and PN532.
- User prefers the assistant to implement and verify, not just propose.

## Development Mode

Current direction is ROS2 Humble integration rather than one monolithic `main.py`.

Key architectural decision:

- `cabinet_logic_node` is the system-level source of truth.
- `ui_node` should show aggregated `/ui/*` data from `cabinet_logic_node`.
- UI should not directly subscribe to raw sensor, actuator, battery, or vision topics for business logic.

## Sync Rule

Local code:

```text
D:\Desktop\Elf2官方资料\workspace
```

Board code:

```bash
~/smart_tool_cabinet/
```

When modifying executable code locally, sync to board with `scp` and rebuild if ROS code changed.
