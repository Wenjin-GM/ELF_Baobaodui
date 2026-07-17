#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="$PROJECT_ROOT/data"
LOG_DIR="$DATA_DIR/desktop_launcher_logs"
mkdir -p "$LOG_DIR"

{
  echo
  echo "===== $(date '+%F %T') stop smart cabinet from desktop ====="
  "$PROJECT_ROOT/stop_all_ros_nodes.sh"
} >>"$LOG_DIR/stop.log" 2>&1