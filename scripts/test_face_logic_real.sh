#!/usr/bin/env bash
# ============================================================================
# Real face_node + cabinet_logic_node integration test
#
# Usage:
#   bash test_face_logic_real.sh [success|failure|all]
#
# success — user faces camera, real recognition expected
# failure — user blocks camera / leaves, timeout expected
#
# Exit codes: 0 = all passed, N = number of failed assertions.
# ============================================================================
set -eo pipefail

MODE="${1:-all}"
case "$MODE" in
  success|failure|all) ;;
  *) echo "Usage: $0 [success|failure|all]"; exit 2 ;;
esac

WS=~/smart_tool_cabinet/ros2_ws
LOG_BASE=~/smart_tool_cabinet/data/ros_logs/face_logic_tests
RUN_TS=$(date +%Y%m%d_%H%M%S)
LOG_DIR="$LOG_BASE/$RUN_TS"
mkdir -p "$LOG_DIR"
exec > >(tee -a "$LOG_DIR/result.txt") 2>&1

cd "$WS"
source /opt/ros/humble/setup.bash
source install/setup.bash
export PYTHONDONTWRITEBYTECODE=1

# ---- pre-cleanup warning ----
echo "This test will STOP these nodes if running:"
echo "  actuator_node, cabinet_logic_node, face_node, scenario_player"
echo "Other nodes (ui_node, env_node, nfc_node) will NOT be touched."
echo ""

# ---- pre-cleanup: only our test nodes ----
for _proc in actuator_node cabinet_logic_node face_node scenario_player; do
  pkill -9 -f "smart_cabinet_nodes.*$_proc" 2>/dev/null || true
done
sleep 1

# ---- state ----
PASS_COUNT=0; FAIL_COUNT=0; FIRST_STEP=1; EXIT_CODE=1; COMPLETED=0
PIDS=()
CURRENT_PHASE=""
CLEANUP_DONE=0

_start_step() { STEP_NAME="$1"; STEP_DESC="$2"; echo ""; echo "--- [$STEP_NAME] $STEP_DESC ---"; }
_pass()   { PASS_COUNT=$((PASS_COUNT+1)); echo "  PASS"; _record_step "PASS" "$*"; }
_fail()   { FAIL_COUNT=$((FAIL_COUNT+1)); EXIT_CODE=$FAIL_COUNT; echo "  FAIL — $*"; _record_step "FAIL" "$*"; }

_record_step() {
  local safe_note
  safe_note=$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "${2:-}" 2>/dev/null || echo '""')
  local entry; entry=$(printf '{"step":"%s","result":"%s","note":%s}' "$STEP_NAME" "$1" "$safe_note")
  if [ "$FIRST_STEP" = "1" ]; then echo "" >> "$RESULT_FILE"; echo -n "    $entry" >> "$RESULT_FILE"; FIRST_STEP=0
  else echo "," >> "$RESULT_FILE"; echo -n "    $entry" >> "$RESULT_FILE"; fi
}

_assert() {
  local desc="$1" pat="$2" src="${3:-/dev/stdin}"
  if grep -qE "$pat" "$src" 2>/dev/null; then _pass "$desc"; else _fail "$desc (expected: $pat)"; fi
}

_logic_log() { echo "$LOG_DIR/cabinet_logic_${CURRENT_PHASE}.log"; }
_face_log()  { echo "$LOG_DIR/face_node_${CURRENT_PHASE}.log"; }
_assert_log()   { _assert "$@" "$(_logic_log)"; }
_assert_flog()  { _assert "$@" "$(_face_log)"; }

_svc() {
  local svc="$1" type="$2" data="$3" out="$4"
  ros2 service call "$svc" "$type" "$data" > "$LOG_DIR/${CURRENT_PHASE}_${out}.txt" 2>&1
  cat "$LOG_DIR/${CURRENT_PHASE}_${out}.txt"
}

# ---- lifecycle ----
start_nodes() {
  ros2 run smart_cabinet_nodes actuator_node --ros-args -p dry_run:=true \
    > "$LOG_DIR/actuator_${CURRENT_PHASE}.log" 2>&1 &
  PIDS+=($!); sleep 1

  ros2 run smart_cabinet_nodes face_node --ros-args \
    -p dry_run:=false \
    -p camera:=/dev/video21 \
    -p face_db:=/home/elf/smart_tool_cabinet/USB/face_auth/face_db \
    -p min_confidence:=0.45 \
    > "$(_face_log)" 2>&1 &
  PIDS+=($!); sleep 3

  ros2 run smart_cabinet_nodes cabinet_logic_node --ros-args \
    -p auth_timeout_sec:=10.0 \
    -p face_min_confidence:=0.45 \
    -p lock_pulse_sec:=0.3 \
    -p simulate_missing_battery:=true \
    -p simulate_missing_vision:=true \
    > "$(_logic_log)" 2>&1 &
  PIDS+=($!); sleep 2
}

stop_nodes() {
  for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done
  for _ in {1..10}; do
    local alive=0
    for pid in "${PIDS[@]}"; do kill -0 "$pid" 2>/dev/null && alive=1 || true; done
    [ $alive -eq 0 ] && break
    sleep 0.3
  done
  for _proc in actuator_node cabinet_logic_node face_node; do
    pkill -9 -f "smart_cabinet_nodes.*$_proc" 2>/dev/null || true
  done
  PIDS=(); sleep 1
}

cleanup() {
  [ $CLEANUP_DONE -eq 0 ] || return
  CLEANUP_DONE=1
  stop_nodes 2>/dev/null || true
  if [ -n "$RESULT_FILE" ]; then
    echo "" >> "$RESULT_FILE"
    echo "  ]," >> "$RESULT_FILE"
    printf '  "pass": %d,\n  "fail": %d,\n  "total": %d,\n' $PASS_COUNT $FAIL_COUNT $((PASS_COUNT+FAIL_COUNT)) >> "$RESULT_FILE"
    if [ $COMPLETED -eq 1 ] && [ $FAIL_COUNT -eq 0 ] && [ $PASS_COUNT -gt 0 ]; then
      EXIT_CODE=0
      echo '  "verdict": "PASS"' >> "$RESULT_FILE"
      echo "REGRESSION PASSED"
    else
      echo '  "verdict": "FAIL"' >> "$RESULT_FILE"
      echo "REGRESSION FAILED (exit=$EXIT_CODE) — see $LOG_DIR"
    fi
    echo "}" >> "$RESULT_FILE"
    echo ""; echo "===== SUMMARY ====="
    echo "pass=$PASS_COUNT  fail=$FAIL_COUNT  total=$((PASS_COUNT+FAIL_COUNT))"
    cat "$RESULT_FILE"; echo ""
  fi
  exit $EXIT_CODE
}
trap cleanup EXIT INT TERM

# ---- summary init ----
RESULT_FILE="$LOG_DIR/summary.json"
cat > "$RESULT_FILE" << EOF
{
  "test": "face_logic real integration",
  "mode": "$MODE",
  "timestamp": "$RUN_TS",
  "steps": [
EOF

# ================================================================== SUCCESS
_wait_for_user() {
  local prompt="$1"
  if [ "${NONINTERACTIVE:-0}" = "1" ]; then
    echo "  NONINTERACTIVE mode — waiting 3s instead of prompting"
    sleep 3
  else
    echo ""
    read -rp "  $prompt  Press Enter to continue..." _
  fi
}

run_success() {
  CURRENT_PHASE="success"
  echo "=============================================="
  echo "  REAL FACE — SUCCESS PATH"
  echo "  Ensure gao mo is facing /dev/video21"
  echo "=============================================="
  _wait_for_user "Gao mo should be facing the camera."

  start_nodes

  _start_step "face_ready" "FaceRecognizer loaded"
  _assert_flog "recognizer ready" "FaceRecognizer ready"

  _start_step "request_open" "trigger auth"
  _svc /cabinet/request_open smart_cabinet_interfaces/srv/RequestOpen \
    '{timeout_sec: 10.0}' request_open
  _assert "accepted" "accepted=True" "$LOG_DIR/${CURRENT_PHASE}_request_open.txt"
  _assert "auth started" "authentication started" "$LOG_DIR/${CURRENT_PHASE}_request_open.txt"
  sleep 1

  echo "  Waiting for face recognition (up to 10s)..."
  sleep 10

  _start_step "state_transition" "STANDBY -> AUTH_PENDING -> USER_AUTHED"
  _assert_log "STANDBY->AUTH" "STANDBY -> AUTH_PENDING"
  _assert_log "AUTH->USER" "AUTH_PENDING -> USER_AUTHED"

  _start_step "user_identified" "gao mo recognized via face"
  _assert_log "gao mo" "高莫"
  _assert_log "face method" "人脸识别"

  _start_step "lock_opened" "door lock triggered"
  _assert_log "lock" "门锁已打开"

  _start_step "nfc_skipped" "auth via face (NFC was skipped)"
  # NFC server not running → call_nfc_action fails → face succeeds.
  # "人脸识别" in the auth log proves NFC was not the auth method.
  _assert_log "face used" "人脸识别"

  _start_step "fan_on" "manual fan ON"
  _svc /cabinet/request_manual_fan smart_cabinet_interfaces/srv/RequestManualFan \
    '{"on": true, "reason": "real_face_test_on"}' fan_on
  _assert "accepted" "accepted=True" "$LOG_DIR/${CURRENT_PHASE}_fan_on.txt"

  _start_step "fan_off" "manual fan OFF"
  _svc /cabinet/request_manual_fan smart_cabinet_interfaces/srv/RequestManualFan \
    '{"on": false, "reason": "real_face_test_off"}' fan_off
  _assert "accepted" "accepted=True" "$LOG_DIR/${CURRENT_PHASE}_fan_off.txt"

  _start_step "inventory" "mock inventory"
  _svc /cabinet/request_inventory smart_cabinet_interfaces/srv/RequestInventory \
    '{reason: real_face_test}' inventory
  _assert "accepted" "accepted=True" "$LOG_DIR/${CURRENT_PHASE}_inventory.txt"
  sleep 3

  _start_step "inventory_state" "CHECKING_AFTER_CLOSE -> back to auth"
  _assert_log "enter checking" "USER_AUTHED -> CHECKING_AFTER_CLOSE"
  _assert_log "back to AUTHED" "CHECKING_AFTER_CLOSE -> ADMIN_AUTHED|CHECKING_AFTER_CLOSE -> USER_AUTHED"

  stop_nodes
}

# ================================================================== FAILURE
run_failure() {
  CURRENT_PHASE="failure"
  echo "=============================================="
  echo "  REAL FACE — FAILURE PATH"
  echo "  Block camera or leave the frame"
  echo "=============================================="
  _wait_for_user "Camera should be blocked or no one in frame."

  start_nodes

  _start_step "face_ready" "FaceRecognizer loaded"
  _assert_flog "recognizer ready" "FaceRecognizer ready"

  _start_step "request_open" "trigger auth (will fail)"
  _svc /cabinet/request_open smart_cabinet_interfaces/srv/RequestOpen \
    '{timeout_sec: 6.0}' request_open
  _assert "accepted" "accepted=True" "$LOG_DIR/${CURRENT_PHASE}_request_open.txt"
  sleep 8

  _start_step "fail_transition_1" "STANDBY -> AUTH_PENDING"
  _assert_log "STANDBY->AUTH" "STANDBY -> AUTH_PENDING"

  _start_step "fail_transition_2" "AUTH_PENDING -> STANDBY"
  _assert_log "AUTH->STANDBY" "AUTH_PENDING -> STANDBY"

  _start_step "fail_reason" "timeout or auth failure logged"
  _assert_log "timeout" "timeout|face unavailable|not recognized|camera open failed"

  _start_step "no_lock" "no lock opened"
  if grep -q "门锁已打开" "$(_logic_log)" 2>/dev/null; then
    _fail "lock should NOT open on failure"
  else
    _pass "lock not opened (correct)"
  fi

  _start_step "no_user_auth" "no USER_AUTHED state"
  if grep -q "USER_AUTHED" "$(_logic_log)" 2>/dev/null; then
    _fail "should not reach USER_AUTHED"
  else
    _pass "USER_AUTHED not reached (correct)"
  fi

  stop_nodes
}

# ================================================================== MAIN
case "$MODE" in
  success) run_success ;;
  failure) run_failure ;;
  all)     run_success; run_failure ;;
esac
COMPLETED=1
