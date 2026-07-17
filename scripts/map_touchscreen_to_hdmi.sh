#!/usr/bin/env bash
set -euo pipefail

# Keep the USB touch panel mapped to the visible HDMI cabinet display.
# The board can expose both HDMI-1 and DSI-1; XInput/GNOME may otherwise
# bind OpenWare/ILI touch coordinates to the DSI area after boot or hotplug.

DISPLAY="${DISPLAY:-:0}"
XAUTHORITY="${XAUTHORITY:-/run/user/1000/gdm/Xauthority}"
OUTPUT="${SMART_CABINET_TOUCH_OUTPUT:-HDMI-1}"
DEVICE_NAME="${SMART_CABINET_TOUCH_DEVICE:-OpenWare Multi-Touch-V5000}"
TRIES="${SMART_CABINET_TOUCH_MAP_TRIES:-60}"
SLEEP_SEC="${SMART_CABINET_TOUCH_MAP_SLEEP:-0.5}"
HOLD_SEC="${SMART_CABINET_TOUCH_MAP_HOLD_SEC:-0}"
HOLD_INTERVAL="${SMART_CABINET_TOUCH_MAP_HOLD_INTERVAL:-2}"

export DISPLAY XAUTHORITY

if ! command -v xinput >/dev/null 2>&1 || ! command -v xrandr >/dev/null 2>&1; then
  echo "touchscreen mapping skipped: xinput/xrandr unavailable"
  exit 0
fi

map_once() {
  local ids id
  ids="$(xinput list 2>/dev/null | sed -n "/${DEVICE_NAME}/s/.*id=\([0-9][0-9]*\).*/\1/p" || true)"
  [[ -n "$ids" ]] || return 1

  while read -r id; do
    [[ -z "$id" ]] && continue
    xinput map-to-output "$id" "$OUTPUT" 2>/dev/null || true
  done <<< "$ids"
  echo "touchscreen mapped to ${OUTPUT}: ${ids}"
  return 0
}

wait_and_map() {
  local i
  for ((i=1; i<=TRIES; i++)); do
    if xrandr --query 2>/dev/null | grep -q "^${OUTPUT} connected"; then
      if map_once; then
        return 0
      fi
    fi
    sleep "$SLEEP_SEC"
  done
  echo "touchscreen mapping skipped: ${DEVICE_NAME} or ${OUTPUT} not ready"
  return 0
}

wait_and_map

if [[ "$HOLD_SEC" != "0" ]]; then
  end=$((SECONDS + HOLD_SEC))
  while (( SECONDS < end )); do
    sleep "$HOLD_INTERVAL"
    if xrandr --query 2>/dev/null | grep -q "^${OUTPUT} connected"; then
      map_once >/dev/null 2>&1 || true
    fi
  done
fi

exit 0