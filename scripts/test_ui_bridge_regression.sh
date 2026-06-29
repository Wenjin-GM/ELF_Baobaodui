#!/usr/bin/env bash
# ============================================================================
# UI bridge regression test — no display needed, ROS-only
#
# Verifies:
#   1. ui_node --test receives /ui/* topics
#   2. --request-open triggers auth via fake face (user + lock in logs)
#   3. --request-fan-on/off reaches actuator (both cabinet & actuator logs)
#   4. --request-inventory updates /ui/inventory
# ============================================================================
set -eo pipefail

WS=~/smart_tool_cabinet/ros2_ws
LOG_BASE=~/smart_tool_cabinet/data/ros_logs/ui_bridge_tests
RUN_TS=$(date +%Y%m%d_%H%M%S)
LOG_DIR="$LOG_BASE/$RUN_TS"
mkdir -p "$LOG_DIR"
exec > >(tee -a "$LOG_DIR/result.txt") 2>&1

cd "$WS"
source /opt/ros/humble/setup.bash
source install/setup.bash
export PYTHONDONTWRITEBYTECODE=1

# ---- pre-cleanup ----
echo "This test will STOP: actuator_node, cabinet_logic_node, scenario_player"
for _proc in actuator_node cabinet_logic_node scenario_player; do
  pkill -9 -f "smart_cabinet_nodes.*$_proc" 2>/dev/null || true
done
sleep 1

# ---- state ----
PASS_COUNT=0; FAIL_COUNT=0; FIRST_STEP=1; EXIT_CODE=1; COMPLETED=0
PIDS=(); CLEANUP_DONE=0

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
_assert_act()  { _assert "$1" "$2" "$LOG_DIR/actuator.log"; }
_assert_logic() { _assert "$1" "$2" "$LOG_DIR/cabinet_logic.log"; }

stop_nodes() {
  for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done
  for _ in {1..10}; do
    local alive=0
    for pid in "${PIDS[@]}"; do kill -0 "$pid" 2>/dev/null && alive=1 || true; done
    [ $alive -eq 0 ] && break; sleep 0.3
  done
  for _proc in actuator_node cabinet_logic_node scenario_player; do
    pkill -9 -f "smart_cabinet_nodes.*$_proc" 2>/dev/null || true
  done
  PIDS=(); sleep 1
}

cleanup() {
  [ $CLEANUP_DONE -eq 0 ] || return; CLEANUP_DONE=1
  stop_nodes 2>/dev/null || true
  if [ -n "$RESULT_FILE" ]; then
    echo "" >> "$RESULT_FILE"; echo "  ]," >> "$RESULT_FILE"
    printf '  "pass": %d,\n  "fail": %d,\n  "total": %d,\n' $PASS_COUNT $FAIL_COUNT $((PASS_COUNT+FAIL_COUNT)) >> "$RESULT_FILE"
    if [ $COMPLETED -eq 1 ] && [ $FAIL_COUNT -eq 0 ] && [ $PASS_COUNT -gt 0 ]; then
      EXIT_CODE=0; echo '  "verdict": "PASS"' >> "$RESULT_FILE"; echo "REGRESSION PASSED"
    else
      echo '  "verdict": "FAIL"' >> "$RESULT_FILE"; echo "REGRESSION FAILED (exit=$EXIT_CODE)"
    fi
    echo "}" >> "$RESULT_FILE"
    echo ""; echo "===== SUMMARY ====="; echo "pass=$PASS_COUNT  fail=$FAIL_COUNT"
    cat "$RESULT_FILE"; echo ""
  fi
  exit $EXIT_CODE
}
trap cleanup EXIT INT TERM

RESULT_FILE="$LOG_DIR/summary.json"
cat > "$RESULT_FILE" << EOF
{ "test": "ui_bridge regression", "timestamp": "$RUN_TS", "steps": [
EOF

# ================================================================== MAIN
echo "========== UI Bridge Regression =========="

# ---- start backend nodes ----
_start_step "start_nodes" "actuator + fake face + cabinet_logic"
ros2 run smart_cabinet_nodes actuator_node --ros-args -p dry_run:=true \
  > "$LOG_DIR/actuator.log" 2>&1 & PIDS+=($!); sleep 1

ros2 run smart_cabinet_nodes scenario_player --ros-args \
  -p mode:=fake_face_action_server -p result_success:=true \
  -p result_user_name:=UIBridgeUser -p result_role:=admin \
  -p result_message:="ui bridge face auth" > "$LOG_DIR/fake_face.log" 2>&1 &
PIDS+=($!); sleep 1

ros2 run smart_cabinet_nodes cabinet_logic_node --ros-args \
  -p auth_timeout_sec:=5.0 -p simulate_missing_battery:=true \
  -p simulate_missing_vision:=true > "$LOG_DIR/cabinet_logic.log" 2>&1 &
PIDS+=($!); sleep 3

_start_step "svc_check" "backend services"
ros2 service list > "$LOG_DIR/svc.txt" 2>&1
_assert "actuator" "/actuator/open_lock" "$LOG_DIR/svc.txt"
_assert "cabinet"  "/cabinet/request_open" "$LOG_DIR/svc.txt"

# ---- ui_node --test: data subscription ----
_start_step "topic_sub" "ui_node --test receives /ui/* data"
timeout 10 ros2 run smart_cabinet_nodes ui_node --test --test-timeout-sec 8 \
  > "$LOG_DIR/ui_test_topic.txt" 2>&1 || true

UI_OUT="$LOG_DIR/ui_test_topic.txt"
_assert "summary>=1"   "summary=[1-9]" "$UI_OUT"
_assert "environment>=1" "environment=[1-9]" "$UI_OUT"
_assert "inventory>=1" "inventory=[1-9]" "$UI_OUT"
_assert "battery>=1"   "battery=[1-9]" "$UI_OUT"

# ---- ui_node --test: request_open ----
_start_step "request_open" "ui_node --test --request-open"
timeout 12 ros2 run smart_cabinet_nodes ui_node --test --request-open \
  --request-open-timeout 5.0 --test-timeout-sec 3 \
  > "$LOG_DIR/ui_test_open.txt" 2>&1 || true
_assert "open accepted" "request_open accepted=True" "$LOG_DIR/ui_test_open.txt"
_assert_logic "request received" "request_open received"
_assert_logic "user=UIBridgeUser" "UIBridgeUser"
_assert_logic "auth success" "通过 人脸识别 认证"
_assert_logic "lock opened" "门锁已打开"
_assert_act "lock dry-run" "\(dry-run\) open_lock"

# ---- ui_node --test: fan ----
_start_step "request_fan_on" "ui_node --test --request-fan-on"
timeout 10 ros2 run smart_cabinet_nodes ui_node --test --request-fan-on \
  --test-timeout-sec 3 > "$LOG_DIR/ui_test_fan_on.txt" 2>&1 || true
_assert "fan on accepted" "request_manual_fan\(on\) accepted=True" "$LOG_DIR/ui_test_fan_on.txt"
_assert_logic "fan on received" "request_manual_fan received: on"
_assert_act "fan on dry-run" "\(dry-run\) set_fan on=True"

_start_step "request_fan_off" "ui_node --test --request-fan-off"
timeout 10 ros2 run smart_cabinet_nodes ui_node --test --request-fan-off \
  --test-timeout-sec 3 > "$LOG_DIR/ui_test_fan_off.txt" 2>&1 || true
_assert "fan off accepted" "request_manual_fan\(off\) accepted=True" "$LOG_DIR/ui_test_fan_off.txt"
_assert_logic "fan off received" "request_manual_fan received: off"
_assert_act "fan off dry-run" "\(dry-run\) set_fan on=False"

# ---- ui_node --test: inventory ----
_start_step "request_inventory" "ui_node --test --request-inventory"
timeout 12 ros2 run smart_cabinet_nodes ui_node --test --request-inventory \
  --test-timeout-sec 3 > "$LOG_DIR/ui_test_inv.txt" 2>&1 || true
_assert "inventory accepted" "request_inventory accepted=True" "$LOG_DIR/ui_test_inv.txt"
_assert_logic "inventory received" "request_inventory received"
_assert_logic "mock used" "vision_node offline; using mock"
_assert_logic "inventory complete" "CHECKING_AFTER_CLOSE -> ADMIN_AUTHED|CHECKING_AFTER_CLOSE -> USER_AUTHED"
_assert "inventory updated" "inventory=([2-9]|[1-9][0-9])" "$LOG_DIR/ui_test_inv.txt"

stop_nodes
COMPLETED=1
