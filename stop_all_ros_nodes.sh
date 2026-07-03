#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="$PROJECT_ROOT/data"
PID_DIR="$DATA_DIR/run"

stop_pid_file() {
  local pid_file="$1"
  local name
  name="$(basename "$pid_file" .pid)"

  [[ -s "$pid_file" ]] || return 0
  local pid
  pid="$(cat "$pid_file")"

  if kill -0 "$pid" 2>/dev/null; then
    echo "stopping $name pid=$pid"
    kill -INT "-$pid" 2>/dev/null || kill -INT "$pid" 2>/dev/null || true
    for _ in $(seq 1 20); do
      if ! kill -0 "$pid" 2>/dev/null; then
        rm -f "$pid_file"
        return 0
      fi
      sleep 0.2
    done
    echo "forcing $name pid=$pid"
    kill -TERM "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    sleep 0.5
    kill -KILL "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
  fi

  rm -f "$pid_file"
}

if [[ -d "$PID_DIR" ]]; then
  for name in ui_node cabinet_logic_node face_node nfc_node actuator_node env_node battery_node; do
    stop_pid_file "$PID_DIR/${name}.pid"
  done
fi

# Fallback cleanup for nodes launched manually or from old scripts.
pkill -f '/smart_cabinet_nodes/lib/smart_cabinet_nodes/ui_node' 2>/dev/null || true
pkill -f '/smart_cabinet_nodes/lib/smart_cabinet_nodes/cabinet_logic_node' 2>/dev/null || true
pkill -f '/smart_cabinet_nodes/lib/smart_cabinet_nodes/face_node' 2>/dev/null || true
pkill -f '/smart_cabinet_nodes/lib/smart_cabinet_nodes/nfc_node' 2>/dev/null || true
pkill -f '/smart_cabinet_nodes/lib/smart_cabinet_nodes/actuator_node' 2>/dev/null || true
pkill -f '/smart_cabinet_nodes/lib/smart_cabinet_nodes/env_node' 2>/dev/null || true
pkill -f '/smart_cabinet_nodes/lib/smart_cabinet_nodes/battery_node' 2>/dev/null || true

# Keep the active-high buzzer quiet after actuator shutdown.
if command -v gpioset >/dev/null 2>&1; then
  gpioset gpiochip3 4=0 2>/dev/null || true
fi

echo "smart cabinet ROS nodes stopped"
