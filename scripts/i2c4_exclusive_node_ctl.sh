#!/usr/bin/env bash
# i2c4_exclusive_node_ctl.sh — ensure env_node and nfc_node never run together.
#
# Usage:
#   bash scripts/i2c4_exclusive_node_ctl.sh env     start env_node, stop nfc_node
#   bash scripts/i2c4_exclusive_node_ctl.sh nfc     start nfc_node, stop env_node
#   bash scripts/i2c4_exclusive_node_ctl.sh none    stop both
#   bash scripts/i2c4_exclusive_node_ctl.sh status  report status
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="$PROJECT_ROOT/data"
PID_DIR="$DATA_DIR/run"
LOCK_DIR="$PID_DIR/i2c4_switch.lockdir"
LOG_DIR="$DATA_DIR/ros_logs/i2c4_switch"
ROS_WS="$PROJECT_ROOT/ros2_ws"

mkdir -p "$PID_DIR" "$LOG_DIR"

# ── pattern helpers ───────────────────────────────────────────────
# Must match BOTH the ros2 run wrapper AND the actual node binary so
# that stop_node never misses a real process (e.g. after setsid).
node_pattern() {
  echo "(ros2 run smart_cabinet_nodes ${1}|/smart_cabinet_nodes/lib/smart_cabinet_nodes/${1})"
}
node_pids()  { pgrep -f "$(node_pattern "$1")" 2>/dev/null || true; }

# ── lock ──────────────────────────────────────────────────────────
acquire_lock() {
  local waited=0
  while ! mkdir "$LOCK_DIR" 2>/dev/null; do
    if [[ $waited -ge 10 ]]; then
      echo "ERROR: could not acquire i2c4 switch lock after 10s" >&2
      exit 1
    fi
    sleep 0.2
    waited=$((waited + 1))
  done
}
release_lock() { rmdir "$LOCK_DIR" 2>/dev/null || true; }

# ── stop ──────────────────────────────────────────────────────────
stop_node() {
  local name="$1"
  local pids
  pids=$(node_pids "$name")

  if [[ -z "$pids" ]]; then
    return 0
  fi

  echo "[i2c4_ctl] stopping $name (pids: $pids) ..."

  # Try process-group kill first (for setsid-launched nodes), then individual.
  for pid in $pids; do
    kill -2 "-$pid" 2>/dev/null || kill -2 "$pid" 2>/dev/null || true
  done

  local waited=0
  while [[ $waited -lt 30 ]]; do
    pids=$(node_pids "$name")
    [[ -z "$pids" ]] && break
    sleep 0.1
    waited=$((waited + 1))
  done

  pids=$(node_pids "$name")
  if [[ -n "$pids" ]]; then
    for pid in $pids; do
      kill -9 "-$pid" 2>/dev/null || kill -9 "$pid" 2>/dev/null || true
    done
    sleep 0.5
  fi

  # Final sweep: any remaining real-node binaries
  pids=$(node_pids "$name")
  if [[ -n "$pids" ]]; then
    echo "[i2c4_ctl] WARNING: $name still alive after kill: $pids" >&2
  else
    echo "[i2c4_ctl] $name stopped"
  fi
}

# ── start ─────────────────────────────────────────────────────────
start_env_node() {
  if [[ -n "$(node_pids env_node)" ]]; then
    echo "[i2c4_ctl] env_node already running"
    return 0
  fi

  set +u
  source /opt/ros/humble/setup.bash
  source "$ROS_WS/install/setup.bash"
  set -u

  echo "[i2c4_ctl] starting env_node ..."
  setsid ros2 run smart_cabinet_nodes env_node \
    --ros-args -p period_sec:=1.0 -p dry_run:=false -p bus:=4 -p address:=68 \
    >"$LOG_DIR/env_node.log" 2>&1 &
  echo "$!" >"$PID_DIR/env_node.pid"
  sleep 0.5
  echo "[i2c4_ctl] env_node started (pid=$(cat "$PID_DIR/env_node.pid"))"
}

start_nfc_node() {
  if [[ -n "$(node_pids nfc_node)" ]]; then
    echo "[i2c4_ctl] nfc_node already running"
    return 0
  fi

  set +u
  source /opt/ros/humble/setup.bash
  source "$ROS_WS/install/setup.bash"
  set -u

  echo "[i2c4_ctl] starting nfc_node on i2c-7 ..."
  setsid ros2 run smart_cabinet_nodes nfc_node \
    --ros-args -p dry_run:=false -p bus:=7 -p address:=36 -p poll_sec:=0.1 \
    >"$LOG_DIR/nfc_node.log" 2>&1 &
  echo "$!" >"$PID_DIR/nfc_node.pid"
  sleep 0.5
  echo "[i2c4_ctl] nfc_node started (pid=$(cat "$PID_DIR/nfc_node.pid"))"
}

# ── dual-run check ────────────────────────────────────────────────
assert_opposite_stopped() {
  local pids
  pids=$(node_pids "$1")
  if [[ -n "$pids" ]]; then
    echo "ERROR: $1 is still running (pids: $pids); refusing to start" >&2
    exit 1
  fi
}

check_dual_run() {
  # Historical name kept for compatibility. NFC is now on i2c-7 and SHT30 is
  # on i2c-4, so env_node and nfc_node may run at the same time.
  return 0
}

# ═══════════════════════════════════════════════════════════════════
CMD="${1:-status}"

acquire_lock
trap release_lock EXIT

case "$CMD" in
  env)
    start_env_node
    ;;
  nfc)
    start_nfc_node
    ;;
  none)
    stop_node env_node
    stop_node nfc_node
    ;;
  status)
    echo "=== i2c4 exclusive node status ==="
    for name in env_node nfc_node; do
      pids=$(node_pids "$name")
      if [[ -n "$pids" ]]; then
        echo "  $name: running ($pids)"
      else
        echo "  $name: stopped"
      fi
    done
    check_dual_run || exit 1
    ;;
  *)
    echo "Usage: $0 {env|nfc|none|status}" >&2
    exit 2
    ;;
esac
