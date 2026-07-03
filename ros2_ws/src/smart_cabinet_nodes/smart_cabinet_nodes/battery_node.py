"""
ROS2 battery_node — reads STM32 PB0 single-wire presence via GPIO.

Publishes /battery/state (std_msgs/String JSON).
"""

from __future__ import annotations

import time

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import String

from .battery_reader import Pb0PollingPresenceReader, Pb0PresenceReader, build_payload
from .common import json_text


class BatteryNode(Node):
    def __init__(self):
        super().__init__("battery_node")
        self.declare_parameter("chip", "gpiochip3")
        self.declare_parameter("line", 7)
        self.declare_parameter("period_sec", 1.0)
        self.declare_parameter("confirm_frames", 2)
        self.declare_parameter("timeout_sec", 8.0)
        self.declare_parameter("poll_mode", False)
        self.declare_parameter("poll_interval_sec", 0.01)
        self.declare_parameter("dry_run", False)

        self.pub = self.create_publisher(String, "/battery/state", 10)
        period = max(0.5, float(self.get_parameter("period_sec").value))
        self.timer = self.create_timer(period, self._tick)

        self._reader = None
        self._last_slots = None
        if not bool(self.get_parameter("dry_run").value):
            try:
                chip = str(self.get_parameter("chip").value)
                line = int(self.get_parameter("line").value)
                if bool(self.get_parameter("poll_mode").value):
                    interval = float(self.get_parameter("poll_interval_sec").value)
                    self._reader = Pb0PollingPresenceReader(chip=chip, line=line, interval_sec=interval)
                    mode = f"poll interval={interval:.3f}s"
                else:
                    self._reader = Pb0PresenceReader(chip=chip, line=line)
                    mode = "edge"
                self.get_logger().info(
                    f"PB0 reader ready on {chip} line {line} ({mode})"
                )
            except Exception as exc:
                self.get_logger().error(f"PB0 reader init failed: {exc}")

    def _tick(self):
        payload = self._read_once()
        self.pub.publish(String(data=json_text(payload)))

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

        while time.monotonic() < deadline and stable < confirm:
            try:
                remaining = max(1.0, deadline - time.monotonic())
                slots, widths = self._reader.read_frame(timeout=remaining)
                total += 1
                last_widths = widths
                if last_slots == slots:
                    stable += 1
                else:
                    stable = 1
                    last_slots = slots
                if stable >= confirm:
                    break
            except Exception as exc:
                self.get_logger().warning(f"PB0 read failed: {exc}")
                break

        if stable >= confirm:
            self._last_slots = last_slots
            return build_payload(last_slots, last_widths, stable, total)
        return build_payload(None, last_widths, stable, total)

    def destroy_node(self):
        if self._reader:
            self._reader.close()
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
