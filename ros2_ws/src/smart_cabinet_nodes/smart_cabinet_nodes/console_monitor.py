from __future__ import annotations

import json
import os
import signal
import sys
import time
from collections import deque
from typing import Any, Dict

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String


class ConsoleMonitor(Node):
    def __init__(self):
        super().__init__("console_monitor")
        qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self.summary: Dict[str, Any] = {}
        self.environment: Dict[str, Any] = {}
        self.inventory: Dict[str, Any] = {}
        self.battery: Dict[str, Any] = {}
        self.auth: Dict[str, Any] = {}
        self.events = deque(maxlen=8)
        self.last_render = 0.0

        self.create_subscription(String, "/ui/summary", self.on_summary, qos)
        self.create_subscription(String, "/ui/environment", self.on_environment, qos)
        self.create_subscription(String, "/ui/inventory", self.on_inventory, qos)
        self.create_subscription(String, "/ui/battery", self.on_battery, qos)
        self.create_subscription(String, "/ui/auth", self.on_auth, qos)
        self.create_subscription(String, "/ui/events", self.on_event, 50)
        self.create_timer(1.0, self.render)

    def parse(self, msg: String) -> Dict[str, Any]:
        try:
            return json.loads(msg.data)
        except Exception:
            return {"raw": msg.data}

    def on_summary(self, msg: String):
        self.summary = self.parse(msg)

    def on_environment(self, msg: String):
        self.environment = self.parse(msg)

    def on_inventory(self, msg: String):
        self.inventory = self.parse(msg)

    def on_battery(self, msg: String):
        self.battery = self.parse(msg)

    def on_auth(self, msg: String):
        self.auth = self.parse(msg)

    def on_event(self, msg: String):
        self.events.appendleft(self.parse(msg))

    def render(self):
        state = self.summary.get("state", "UNKNOWN")
        user = self.summary.get("current_user") or {}
        actuator = self.summary.get("actuator") or {}
        env = self.environment or self.summary.get("environment") or {}
        battery = self.battery or self.summary.get("battery") or {}
        inventory = self.inventory or self.summary.get("inventory") or {}
        auth = self.auth or self.summary.get("auth") or {}

        temp = env.get("temperature", "--")
        humidity = env.get("humidity", "--")
        fan_on = actuator.get("fan_on", env.get("fan_on", False))
        lock_busy = actuator.get("lock_busy", False)
        buzzer_busy = actuator.get("buzzer_busy", False)
        box_present = battery.get("box_present", False)
        slots = battery.get("slots") or []
        normal = inventory.get("is_normal", True)
        inventory_msg = inventory.get("message", "no inventory yet")
        auth_msg = auth.get("message", "")

        lines = [
            "Smart Cabinet ROS Monitor",
            "Press Ctrl+C to stop all nodes.",
            "",
            f"State: {state}",
            f"User: {user.get('name', '-') or '-'} ({user.get('role', '-') or '-'})",
            f"Environment: T={temp} C, H={humidity} %RH",
            f"Actuator: fan={'ON' if fan_on else 'OFF'}, lock_busy={lock_busy}, buzzer_busy={buzzer_busy}",
            f"Battery mock/state: box_present={box_present}, slots={slots}",
            f"Inventory: normal={normal}, message={inventory_msg}",
            f"Auth: success={auth.get('success', '-')}, message={auth_msg}",
            "",
            "Recent events:",
        ]
        if self.events:
            for event in list(self.events):
                lines.append(
                    f"- {event.get('timestamp', '')} "
                    f"[{event.get('level', 'info')}] "
                    f"{event.get('type', '-')}: {event.get('content', event.get('message', ''))}"
                )
        else:
            lines.append("- waiting for events...")

        sys.stdout.write("\033[2J\033[H" + "\n".join(lines) + "\n")
        sys.stdout.flush()


def main(args=None):
    rclpy.init(args=args)
    node = ConsoleMonitor()
    stopping = False

    def handle_signal(signum, _frame):
        nonlocal stopping
        stopping = True
        node.get_logger().info(f"console monitor received signal {signum}")

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        while rclpy.ok() and not stopping:
            rclpy.spin_once(node, timeout_sec=0.2)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
