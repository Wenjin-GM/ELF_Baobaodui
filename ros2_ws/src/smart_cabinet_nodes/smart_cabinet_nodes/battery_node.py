"""
ROS2 battery_node — reads STM32 PB0 single-wire presence via GPIO.

Publishes /battery/state (std_msgs/String JSON).
"""

from __future__ import annotations

import json
import threading
import time

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import String

from .battery_reader import (
    GatedPresenceReader,
    Pb0PollingPresenceReader,
    Pb0PresenceReader,
    TwoWirePresenceReader,
    build_payload,
)
from .common import DATA_DIR, ensure_data_dirs, json_text


LAST_GOOD_PATH = DATA_DIR / "battery" / "last_good_state.json"


class BatteryNode(Node):
    def __init__(self):
        super().__init__("battery_node")
        self.declare_parameter("protocol", "gated")
        self.declare_parameter("chip", "gpiochip3")
        self.declare_parameter("data_chip", "gpiochip3")
        self.declare_parameter("data_line", 7)
        self.declare_parameter("frame_chip", "gpiochip3")
        self.declare_parameter("frame_line", 1)
        self.declare_parameter("clk_chip", "gpiochip4")
        self.declare_parameter("clk_line", 18)
        self.declare_parameter("line", 7)
        self.declare_parameter("period_sec", 3.0)
        self.declare_parameter("confirm_frames", 2)
        self.declare_parameter("timeout_sec", 8.0)
        self.declare_parameter("poll_mode", True)
        self.declare_parameter("poll_interval_sec", 0.0)
        self.declare_parameter("change_confirm_frames", 2)
        self.declare_parameter("allow_all_empty_clear", True)
        self.declare_parameter("frame_gap_reset_ms", 150.0)
        self.declare_parameter("dry_run", False)

        self.pub = self.create_publisher(String, "/battery/state", 10)
        period = max(0.5, float(self.get_parameter("period_sec").value))
        self.timer = self.create_timer(period, self._tick)

        self._reader = None
        self._payload_lock = threading.Lock()
        self._payload = build_payload(None, [], 0, 0)
        self._last_good_payload = None
        self._load_last_good_payload()
        self._candidate_slots = None
        self._candidate_frames = 0
        self._candidate_payload = None
        self._stop_event = threading.Event()
        self._worker = None
        if not bool(self.get_parameter("dry_run").value):
            try:
                chip = str(self.get_parameter("chip").value)
                protocol = str(self.get_parameter("protocol").value).lower()
                if protocol == "gated":
                    data_chip = str(self.get_parameter("data_chip").value)
                    data_line = int(self.get_parameter("data_line").value)
                    frame_chip = str(self.get_parameter("frame_chip").value)
                    frame_line = int(self.get_parameter("frame_line").value)
                    self._reader = GatedPresenceReader(
                        chip=chip,
                        data_chip=data_chip,
                        data_line=data_line,
                        frame_chip=frame_chip,
                        frame_line=frame_line,
                    )
                    mode = (
                        f"PB0/PB1 gated data={data_chip}:{data_line} "
                        f"frame={frame_chip}:{frame_line}"
                    )
                elif protocol == "twowire":
                    data_chip = str(self.get_parameter("data_chip").value)
                    data_line = int(self.get_parameter("data_line").value)
                    clk_chip = str(self.get_parameter("clk_chip").value)
                    clk_line = int(self.get_parameter("clk_line").value)
                    frame_gap = float(self.get_parameter("frame_gap_reset_ms").value)
                    self._reader = TwoWirePresenceReader(
                        chip=chip,
                        data_chip=data_chip,
                        data_line=data_line,
                        clk_chip=clk_chip,
                        clk_line=clk_line,
                        frame_gap_reset_ms=frame_gap,
                    )
                    mode = (
                        f"PB0/PB1 two-wire data={data_chip}:{data_line} "
                        f"clk={clk_chip}:{clk_line}"
                    )
                else:
                    line = int(self.get_parameter("line").value)
                    if bool(self.get_parameter("poll_mode").value):
                        interval = float(self.get_parameter("poll_interval_sec").value)
                        self._reader = Pb0PollingPresenceReader(chip=chip, line=line, interval_sec=interval)
                        mode = f"legacy PB0 poll line={line} interval={interval:.3f}s"
                    else:
                        self._reader = Pb0PresenceReader(chip=chip, line=line)
                        mode = f"legacy PB0 edge line={line}"
                self.get_logger().info(
                    f"battery reader ready on {chip} ({mode})"
                )
                self._worker = threading.Thread(target=self._read_loop, daemon=True)
                self._worker.start()
            except Exception as exc:
                self.get_logger().error(f"battery reader init failed: {exc}")
        else:
            self.get_logger().warning("battery_node dry_run=true; publishing offline payload")

    def _tick(self):
        with self._payload_lock:
            payload = dict(self._payload)
        self.pub.publish(String(data=json_text(payload)))

    def _read_loop(self):
        self.get_logger().info("battery reader loop started")
        while not self._stop_event.is_set():
            try:
                raw_payload = self._read_once()
            except Exception as exc:
                self.get_logger().warning(f"battery reader loop error: {exc}")
                raw_payload = build_payload(None, [], 0, 0)

            payload = self._apply_state(raw_payload)
            with self._payload_lock:
                self._payload = payload
            if payload.get("status_valid"):
                state = "stale" if payload.get("stale") else "accepted"
                self.get_logger().info(
                    f"battery read {state}: slots={payload.get('slots')} "
                    f"mask={payload.get('presence_mask')} "
                    f"widths={payload.get('pulse_widths_ms')}"
                )
            else:
                self.get_logger().warning("battery read produced offline payload")

    def _apply_state(self, raw_payload):
        """Accept only stable real states; never persist fallback payloads."""
        if not raw_payload.get("status_valid"):
            self._reset_candidate()
            return self._last_or_offline(
                raw_payload,
                "battery read failed; keeping last stable battery state",
            )

        slots = self._payload_slots(raw_payload)
        current_slots = self._payload_slots(self._last_good_payload)
        allow_all_empty_clear = bool(self.get_parameter("allow_all_empty_clear").value)

        if not any(slots):
            self._reset_candidate()
            if current_slots is not None and any(current_slots) and not allow_all_empty_clear:
                return self._last_or_offline(
                    raw_payload,
                    "battery reader reported all-empty; keeping last known non-empty battery state",
                    possible_empty_transition=True,
                )
            return self._accept_payload(raw_payload)

        if current_slots is None or slots == current_slots:
            self._reset_candidate()
            return self._accept_payload(raw_payload)

        stable_frames = max(1, int(raw_payload.get("stable_frames") or 1))
        if self._candidate_slots == slots:
            self._candidate_frames += stable_frames
        else:
            self._candidate_slots = list(slots)
            self._candidate_frames = stable_frames
        self._candidate_payload = dict(raw_payload)

        change_confirm = max(
            int(self.get_parameter("confirm_frames").value),
            int(self.get_parameter("change_confirm_frames").value),
        )
        if self._candidate_frames >= change_confirm:
            self.get_logger().info(
                f"battery accepted state change: {current_slots} -> {slots} "
                f"after {self._candidate_frames}/{change_confirm} frames"
            )
            return self._accept_payload(raw_payload)

        return self._last_or_offline(
            raw_payload,
            (
                f"battery candidate state {slots} not confirmed yet "
                f"({self._candidate_frames}/{change_confirm}); keeping last stable state"
            ),
            candidate_slots=slots,
            candidate_frames=self._candidate_frames,
        )

    def _read_once(self):
        if self._reader is None:
            return build_payload(None, [], 0, 0)

        confirm = max(1, int(self.get_parameter("confirm_frames").value))
        timeout = max(1.0, float(self.get_parameter("timeout_sec").value))
        deadline = time.monotonic() + timeout
        last_slots = None
        stable = 0
        total = 0
        last_widths = []
        last_info = {}

        while time.monotonic() < deadline and stable < confirm:
            try:
                remaining = max(1.0, deadline - time.monotonic())
                read_with_info = getattr(self._reader, "read_frame_with_info", None)
                if read_with_info is not None:
                    slots, widths, info = read_with_info(timeout=remaining)
                else:
                    slots, widths = self._reader.read_frame(timeout=remaining)
                    info = {}
                total += 1
                last_widths = widths
                last_info = info
                if last_slots == slots:
                    stable += 1
                else:
                    stable = 1
                    last_slots = slots
                if stable >= confirm:
                    break
            except Exception as exc:
                self.get_logger().warning(f"battery read failed: {exc}")
                break

        if stable >= confirm:
            return build_payload(
                last_slots,
                last_widths,
                stable,
                total,
                extra={"frame_info": last_info},
            )
        return build_payload(None, last_widths, stable, total)

    def _payload_slots(self, payload):
        if not payload or not payload.get("status_valid"):
            return None
        slots = payload.get("slots", [])
        if len(slots) < 4:
            return None
        return [bool(item) for item in slots[:4]]

    def _accept_payload(self, payload):
        accepted = dict(payload)
        for key in (
            "stale",
            "possible_empty_transition",
            "candidate_slots",
            "candidate_frames",
            "error",
        ):
            accepted.pop(key, None)
        accepted["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        self._last_good_payload = dict(accepted)
        if any(accepted.get("slots", [])):
            self._save_last_good_payload(accepted)
        return accepted

    def _last_or_offline(self, raw_payload, error, **extra):
        if self._last_good_payload is None:
            fallback = dict(raw_payload)
            fallback["error"] = error
            fallback.update(extra)
            return fallback

        fallback = dict(self._last_good_payload)
        fallback["stale"] = True
        fallback["error"] = error
        fallback["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        fallback["observed_slots"] = raw_payload.get("slots", [])
        fallback["observed_presence_mask"] = raw_payload.get("presence_mask")
        fallback["observed_pulse_widths_ms"] = raw_payload.get("pulse_widths_ms", [])
        fallback["stable_frames"] = raw_payload.get("stable_frames", 0)
        fallback["total_frames"] = raw_payload.get("total_frames", 0)
        fallback.update(extra)
        return fallback

    def _reset_candidate(self):
        self._candidate_slots = None
        self._candidate_frames = 0
        self._candidate_payload = None

    def _load_last_good_payload(self):
        try:
            if not LAST_GOOD_PATH.exists():
                return
            payload = json.loads(LAST_GOOD_PATH.read_text(encoding="utf-8"))
            if payload.get("status_valid") and any(payload.get("slots", [])):
                clean_payload = dict(payload)
                for key in (
                    "stale",
                    "possible_empty_transition",
                    "candidate_slots",
                    "candidate_frames",
                    "observed_slots",
                    "observed_presence_mask",
                    "observed_pulse_widths_ms",
                    "error",
                ):
                    clean_payload.pop(key, None)
                payload = dict(clean_payload)
                payload["stale"] = True
                payload["error"] = "loaded last stable non-empty battery state"
                payload["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                self._last_good_payload = clean_payload
                self._payload = payload
                self.get_logger().info(
                    f"loaded last battery state: slots={payload.get('slots')} "
                    f"mask={payload.get('presence_mask')}"
                )
        except Exception as exc:
            self.get_logger().warning(f"load last battery state failed: {exc}")

    def _save_last_good_payload(self, payload):
        try:
            ensure_data_dirs()
            LAST_GOOD_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            self.get_logger().warning(f"save last battery state failed: {exc}")

    def destroy_node(self):
        self._stop_event.set()
        if self._reader:
            self._reader.close()
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=1.0)
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = BatteryNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
