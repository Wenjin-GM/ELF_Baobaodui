#!/usr/bin/env bash
# ============================================================================
# cabinet_logic_node regression test — parameterised, self-asserting
#
# Usage:
#   bash test_cabinet_regression.sh [success|failure|all]
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
LOG_BASE=~/smart_tool_cabinet/data/ros_logs/regression_tests
RUN_TS=$(date +%Y%m%d_%H%M%S)
LOG_DIR="$LOG_BASE/$RUN_TS"
mkdir -p "$LOG_DIR"

# ---- full console capture to result.txt ----
exec > >(tee -a "$LOG_DIR/result.txt") 2>&1

cd "$WS"
source /opt/ros/humble/setup.bash
source install/setup.bash
export PYTHONDONTWRITEBYTECODE=1

# ---- kill only this test's nodes, never user's manual debug nodes ----
echo "--- pre-cleanup: killing stale test nodes ---"
for _proc in actuator_node cabinet_logic_node scenario_player; do
  pkill -9 -f "smart_cabinet_nodes.*$_proc" 2>/dev/null || true
done
sleep 1

# ------------------------------------------------------------------ state
# Start pessimistic — only clear to 0 when all assertions pass.
# Any unexpected crash (set -e) will exit with this non-zero value.
PASS_COUNT=0; FAIL_COUNT=0; FIRST_STEP=1; EXIT_CODE=1; COMPLETED=0
PIDS=()
CURRENT_PHASE=""
CLEANUP_DONE=0

_start_step() { STEP_NAME="$1"; STEP_DESC="$2"; echo ""; echo "--- [$STEP_NAME] $STEP_DESC ---"; }
_pass()   { PASS_COUNT=$((PASS_COUNT+1)); echo "  PASS"; _record_step "PASS" "$*"; }
_fail()   { FAIL_COUNT=$((FAIL_COUNT+1)); EXIT_CODE=$FAIL_COUNT; echo "  FAIL — $*"; _record_step "FAIL" "$*"; }

# JSON-safe string via sys.argv (never embed untrusted text in Python source)
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

# file path for current phase's cabinet_logic log
_logic_log() { echo "$LOG_DIR/cabinet_logic_${CURRENT_PHASE}.log"; }

_assert_log() {
  _assert "$@" "$(_logic_log)"
}

_svc() {
  local svc="$1" type="$2" data="$3" out="$4"
  ros2 service call "$svc" "$type" "$data" > "$LOG_DIR/${CURRENT_PHASE}_${out}.txt" 2>&1
  cat "$LOG_DIR/${CURRENT_PHASE}_${out}.txt"
}

# ------------------------------------------------------------------ lifecycle
start_nodes() {
  local face_ok="${1:-true}" face_user="${2:-TestUser}" face_role="${3:-user}" face_msg="${4:-scenario face authenticated}"
  ros2 run smart_cabinet_nodes actuator_node --ros-args -p dry_run:=true \
    > "$LOG_DIR/actuator_${CURRENT_PHASE}.log" 2>&1 &
  PIDS+=($!); sleep 1
  ros2 run smart_cabinet_nodes scenario_player --ros-args \
    -p mode:=fake_face_action_server -p result_success:="$face_ok" \
    -p result_user_name:="$face_user" -p result_role:="$face_role" \
    -p result_message:="$face_msg" -p result_delay_sec:=1.0 \
    > "$LOG_DIR/fake_face_${CURRENT_PHASE}.log" 2>&1 &
  PIDS+=($!); sleep 1
  ros2 run smart_cabinet_nodes cabinet_logic_node --ros-args \
    -p simulate_missing_battery:=true -p simulate_missing_vision:=true \
    -p auth_timeout_sec:=5.0 > "$(_logic_log)" 2>&1 &
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
  pkill -9 -f "smart_cabinet_nodes.*actuator_node" 2>/dev/null || true
  pkill -9 -f "smart_cabinet_nodes.*scenario_player" 2>/dev/null || true
  pkill -9 -f "smart_cabinet_nodes.*cabinet_logic_node" 2>/dev/null || true
  PIDS=(); sleep 1
}

cleanup() {
  # re-entry guard — trap may fire multiple times (EXIT + INT)
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
    else
      echo '  "verdict": "FAIL"' >> "$RESULT_FILE"
    fi
    echo "}" >> "$RESULT_FILE"
    echo ""; echo "===== SUMMARY ====="
    echo "pass=$PASS_COUNT  fail=$FAIL_COUNT  total=$((PASS_COUNT+FAIL_COUNT))"
    cat "$RESULT_FILE"; echo ""
    if [ $COMPLETED -eq 1 ] && [ $FAIL_COUNT -eq 0 ] && [ $PASS_COUNT -gt 0 ]; then
      echo "REGRESSION PASSED"
    else
      echo "REGRESSION FAILED (exit=$EXIT_CODE) — see $LOG_DIR"
    fi
  fi
  exit $EXIT_CODE
}
trap cleanup EXIT INT TERM

# ------------------------------------------------------------------ init summary
RESULT_FILE="$LOG_DIR/summary.json"
cat > "$RESULT_FILE" << EOF
{
  "test": "cabinet_logic_node regression",
  "mode": "$MODE",
  "timestamp": "$RUN_TS",
  "steps": [
EOF

# ================================================================== SUCCESS
run_success() {
  CURRENT_PHASE="success"
  echo "========== SUCCESS PATH =========="
  start_nodes "true" "TestUser" "user" "scenario face authenticated"

  _start_step "svc_list" "cabinet & actuator services"
  ros2 service list > "$LOG_DIR/${CURRENT_PHASE}_svc.txt" 2>&1
  _assert "actuator" "/actuator/open_lock" "$LOG_DIR/${CURRENT_PHASE}_svc.txt"
  _assert "cabinet"  "/cabinet/request_open" "$LOG_DIR/${CURRENT_PHASE}_svc.txt"

  _start_step "action_list" "auth actions"
  ros2 action list > "$LOG_DIR/${CURRENT_PHASE}_act.txt" 2>&1
  _assert "face action" "/auth/authenticate_face" "$LOG_DIR/${CURRENT_PHASE}_act.txt"

  _start_step "request_open" "accept authentication"
  _svc /cabinet/request_open smart_cabinet_interfaces/srv/RequestOpen \
    '{timeout_sec: 5.0}' request_open
  _assert "accepted" "accepted=True" "$LOG_DIR/${CURRENT_PHASE}_request_open.txt"
  _assert "auth started" "authentication started" "$LOG_DIR/${CURRENT_PHASE}_request_open.txt"
  sleep 3

  _start_step "state_transition" "STANDBY -> AUTH_PENDING -> USER_AUTHED"
  _assert_log "STANDBY->AUTH_PENDING" "STANDBY -> AUTH_PENDING"
  _assert_log "AUTH_PENDING->USER_AUTHED" "AUTH_PENDING -> USER_AUTHED"

  _start_step "auth_event" "TestUser authenticated via face"
  _assert_log "user auth" "TestUser 通过 人脸识别 认证"

  _start_step "lock_event" "door lock opened"
  _assert_log "lock opened" "门锁已打开"

  _start_step "nfc_skip" "auth worked without NFC (face only)"
  _assert_log "face auth" "人脸识别 认证"

  _start_step "fan_on" "manual fan ON accepted"
  _svc /cabinet/request_manual_fan smart_cabinet_interfaces/srv/RequestManualFan \
    '{"on": true, "reason": "test_on"}' fan_on
  _assert "accepted" "accepted=True" "$LOG_DIR/${CURRENT_PHASE}_fan_on.txt"

  _start_step "fan_off" "manual fan OFF accepted"
  _svc /cabinet/request_manual_fan smart_cabinet_interfaces/srv/RequestManualFan \
    '{"on": false, "reason": "test_off"}' fan_off
  _assert "accepted" "accepted=True" "$LOG_DIR/${CURRENT_PHASE}_fan_off.txt"

  _start_step "inventory" "mock inventory triggers"
  _svc /cabinet/request_inventory smart_cabinet_interfaces/srv/RequestInventory \
    '{reason: test}' inventory
  _assert "accepted" "accepted=True" "$LOG_DIR/${CURRENT_PHASE}_inventory.txt"
  sleep 3

  _start_step "inventory_state_1" "enters CHECKING_AFTER_CLOSE"
  _assert_log "enter checking" "USER_AUTHED -> CHECKING_AFTER_CLOSE"

  _start_step "inventory_state_2" "returns to STANDBY with mock"
  _assert_log "back to STANDBY" "CHECKING_AFTER_CLOSE -> STANDBY"
  _assert_log "mock used" "vision_node offline; using mock inventory result"

  stop_nodes
}

# ================================================================== FAILURE
run_failure() {
  CURRENT_PHASE="failure"
  echo "========== FAILURE PATH =========="
  start_nodes "false" "TestUser" "user" "scenario face rejected"

  _start_step "svc_list" "services available"
  ros2 service list > "$LOG_DIR/${CURRENT_PHASE}_svc.txt" 2>&1
  _assert "cabinet" "/cabinet/request_open" "$LOG_DIR/${CURRENT_PHASE}_svc.txt"

  _start_step "request_open" "accept (will fail)"
  _svc /cabinet/request_open smart_cabinet_interfaces/srv/RequestOpen \
    '{timeout_sec: 5.0}' request_open
  _assert "accepted" "accepted=True" "$LOG_DIR/${CURRENT_PHASE}_request_open.txt"
  sleep 4

  _start_step "fail_transition_1" "STANDBY -> AUTH_PENDING"
  _assert_log "STANDBY->AUTH" "STANDBY -> AUTH_PENDING"

  _start_step "fail_transition_2" "AUTH_PENDING -> STANDBY (recovery)"
  _assert_log "AUTH->STANDBY" "AUTH_PENDING -> STANDBY"

  _start_step "fail_reason" "face rejected logged"
  _assert_log "rejected" "scenario face rejected"

  _start_step "no_lock" "no lock opened on failure"
  if grep -q "门锁已打开" "$(_logic_log)" 2>/dev/null; then
    _fail "lock should NOT open on auth failure"
  else
    _pass "lock not opened (correct)"
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
