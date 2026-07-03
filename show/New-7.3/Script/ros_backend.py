#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ROS2 backend adapter for the PyQt touch UI."""

from __future__ import annotations

import json
import threading
from typing import Any, Dict, List

import numpy as np
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap


class RosBackend(QObject):
    summary_updated = pyqtSignal(dict)
    env_updated = pyqtSignal(dict)
    auth_updated = pyqtSignal(dict)
    tools_updated = pyqtSignal(dict)
    charging_updated = pyqtSignal(dict)
    system_state_changed = pyqtSignal(str)
    event_added = pyqtSignal(dict)
    alarm_raised = pyqtSignal(dict)
    preview_frame = pyqtSignal(QImage)

    def __init__(self):
        super().__init__()
        import rclpy
        from rclpy.executors import MultiThreadedExecutor
        from rclpy.node import Node
        from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
        from sensor_msgs.msg import Image
        from std_msgs.msg import String
        from std_srvs.srv import Trigger
        from smart_cabinet_interfaces.srv import RequestInventory, RequestManualFan, RequestOpen, RequestTempUnlock, UpdateEnvThresholds

        self.rclpy = rclpy
        self.RequestInventory = RequestInventory
        self.RequestManualFan = RequestManualFan
        self.RequestOpen = RequestOpen
        self.RequestTempUnlock = RequestTempUnlock
        self.UpdateEnvThresholds = UpdateEnvThresholds
        self.Trigger = Trigger
        self._owns_context = not rclpy.ok()
        if self._owns_context:
            rclpy.init(args=None)

        self.node = Node("ui_node")
        self.executor = MultiThreadedExecutor(num_threads=2)
        self.executor.add_node(self.node)
        self._spin_thread: threading.Thread | None = None
        self._running = False
        self.fan_on = False

        qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )

        self.node.create_subscription(String, "/ui/summary", self._on_summary, qos)
        self.node.create_subscription(String, "/ui/environment", self._on_environment, qos)
        self.node.create_subscription(String, "/ui/inventory", self._on_inventory, qos)
        self.node.create_subscription(String, "/ui/battery", self._on_battery, qos)
        self.node.create_subscription(String, "/ui/auth", self._on_auth, qos)
        self.node.create_subscription(String, "/ui/events", self._on_event, 50)
        self.node.create_subscription(Image, "/face/preview", self._on_preview, 10)

        self.open_client = self.node.create_client(RequestOpen, "/cabinet/request_open")
        self.inventory_client = self.node.create_client(RequestInventory, "/cabinet/request_inventory")
        self.fan_client = self.node.create_client(RequestManualFan, "/cabinet/request_manual_fan")
        self.temp_unlock_client = self.node.create_client(RequestTempUnlock, "/cabinet/request_temp_unlock")
        self.logout_client = self.node.create_client(Trigger, "/cabinet/logout")
        self.env_thresholds_client = self.node.create_client(UpdateEnvThresholds, "/cabinet/update_env_thresholds")

    def start(self):
        if self._running:
            return
        self._running = True
        self._spin_thread = threading.Thread(target=self.executor.spin, daemon=True)
        self._spin_thread.start()
        self.node.get_logger().info("ui_node RosBackend started")

    def stop(self):
        if not self._running:
            return
        self._running = False
        self.executor.shutdown()
        self.node.destroy_node()
        if self._owns_context and self.rclpy.ok():
            self.rclpy.shutdown()

    def request_open_cabinet(self, timeout_sec: float = 5.0):
        req = self.RequestOpen.Request()
        req.timeout_sec = float(timeout_sec)
        self._call_service(self.open_client, req, "request_open")

    def request_inventory(self, reason: str = "ui_request"):
        req = self.RequestInventory.Request()
        req.reason = reason
        self._call_service(self.inventory_client, req, "request_inventory")

    def request_manual_fan(self, on: bool, reason: str = "ui_manual"):
        req = self.RequestManualFan.Request()
        req.on = bool(on)
        req.reason = reason
        self._call_service(self.fan_client, req, "request_manual_fan")

    def request_temp_unlock(self):
        req = self.RequestTempUnlock.Request()
        self._call_service(self.temp_unlock_client, req, "request_temp_unlock")

    def request_logout(self):
        req = self.Trigger.Request()
        self._call_service(self.logout_client, req, "request_logout")

    def simulate_auth_success(self, user_name: str = "demo_user", role: str = "user"):
        self.request_open_cabinet()

    def update_env_thresholds(self, humidity_on: float, humidity_off: float, temp_on: float, temp_off: float):
        """Call /cabinet/update_env_thresholds service (single source of truth)."""
        req = self.UpdateEnvThresholds.Request()
        req.humidity_on = float(humidity_on)
        req.humidity_off = float(humidity_off)
        req.temp_on = float(temp_on)
        req.temp_off = float(temp_off)
        self._call_service(self.env_thresholds_client, req, "update_env_thresholds")

    def simulate_auth_failed(self):
        self.event_added.emit({"type": "auth", "content": "auth failed requested from UI", "level": "warning"})

    def simulate_door_opened(self):
        self.request_open_cabinet()

    def simulate_door_closed(self):
        self.request_inventory("door_closed")

    def simulate_alarm(self, alarm_type: str = "test_alarm"):
        self.alarm_raised.emit({"type": alarm_type, "level": "warning", "message": alarm_type})

    def _call_service(self, client, request, name: str, timeout_sec: float = 2.0):
        if not client.wait_for_service(timeout_sec=timeout_sec):
            message = f"{name} service not ready"
            self.node.get_logger().warning(message)
            self.event_added.emit({"type": "ui", "content": message, "level": "warning"})
            return
        future = client.call_async(request)
        future.add_done_callback(lambda done: self._on_service_done(name, done))

    def _on_service_done(self, name: str, future):
        try:
            result = future.result()
            accepted = getattr(result, "accepted", getattr(result, "success", None))
            message = getattr(result, "message", "")
            content = f"{name} response: accepted={accepted}, message={message}"
            level = "info" if accepted is not False else "warning"
        except Exception as exc:
            content = f"{name} failed: {exc}"
            level = "warning"
        self.node.get_logger().info(content)
        self.event_added.emit({"type": "ui", "content": content, "level": level})

    def _on_preview(self, msg):
        """Convert /face/preview ROS Image to QImage in ROS thread."""
        try:
            arr = np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.width, -1)
            if arr.shape[2] == 4:
                fmt = QImage.Format_RGBA8888
            elif arr.shape[2] == 3:
                arr = arr[..., ::-1].copy()  # BGR → RGB, force contiguous
                fmt = QImage.Format_RGB888
            else:
                fmt = QImage.Format_Grayscale8
            qimg = QImage(arr.data, msg.width, msg.height, arr.strides[0], fmt).copy()
            self.preview_frame.emit(qimg)
        except Exception as exc:
            self.node.get_logger().error(f"preview decode failed: {exc}")

    def _loads(self, text: str) -> Dict[str, Any]:
        try:
            return json.loads(text)
        except Exception as exc:
            self.node.get_logger().warning(f"invalid UI JSON: {exc}")
            return {}

    def _on_summary(self, msg):
        data = self._loads(msg.data)
        self.summary_updated.emit(data)
        state = data.get("state")
        if state:
            self.system_state_changed.emit(str(state))
        auth = data.get("auth") or {}
        if auth:
            self.auth_updated.emit(self._normalize_auth(auth))

    def _on_environment(self, msg):
        data = self._loads(msg.data)
        self.fan_on = bool(data.get("fan_on", False))
        self.env_updated.emit(
            {
                "temperature": data.get("temperature") if data.get("temperature") is not None else "--",
                "humidity": data.get("humidity") if data.get("humidity") is not None else "--",
                "fan_on": self.fan_on,
                "fan_purpose": "auto/manual" if self.fan_on else "standby",
                "alarm_on": bool(data.get("alarm_on", False)),
                "humidity_on": data.get("humidity_on", 55),
                "humidity_off": data.get("humidity_off", 50),
                "temp_on": data.get("temp_on", 35),
                "temp_off": data.get("temp_off", 30),
                "timestamp": data.get("timestamp", ""),
            }
        )

    def _on_inventory(self, msg):
        data = self._loads(msg.data)
        self.tools_updated.emit({"zones": self._normalize_zones(data.get("zones", [])), "checking": False})

    def _on_battery(self, msg):
        data = self._loads(msg.data)
        slots = data.get("slots") or [False, False, False, False]
        self.charging_updated.emit(
            {
                "module_online": bool(data.get("module_online", False)),
                "status_valid": bool(data.get("status_valid", False)),
                "box_present": bool(data.get("box_present", any(slots))),
                "relay_on": bool(data.get("relay_on", False)),
                "slots": [bool(item) for item in slots[:4]],
                "timestamp": data.get("timestamp", ""),
            }
        )

    def _on_auth(self, msg):
        self.auth_updated.emit(self._normalize_auth(self._loads(msg.data)))

    def _on_event(self, msg):
        event = self._loads(msg.data)
        self.event_added.emit(event)
        if event.get("level") == "warning":
            self.alarm_raised.emit(event)

    def _normalize_auth(self, data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "success": bool(data.get("success", False)),
            "user_name": data.get("user_name") or data.get("name") or "",
            "role": data.get("role") or "user",
            "method": data.get("method") or "",
            "card_uid": data.get("uid") or data.get("card_uid") or "",
            "confidence": float(data.get("confidence", 0.0) or 0.0),
            "timestamp": data.get("timestamp", ""),
        }

    def _normalize_zones(self, zones: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized = []
        for index in range(5):
            raw = zones[index] if index < len(zones) else {}
            registered = int(raw.get("registered", 0) or 0)
            current = int(raw.get("current", registered) or 0)
            status = str(raw.get("status", "normal"))
            if status == "normal":
                status_text = "正常"
            elif status == "missing":
                status_text = "缺失"
            elif status == "misplaced":
                status_text = "错放"
            else:
                status_text = status
            normalized.append(
                {
                    "zone_id": int(raw.get("zone_id", index + 1) or index + 1),
                    "zone_name": raw.get("zone_name", f"zone_{index + 1}"),
                    "registered": registered,
                    "current": current,
                    "borrowed": int(raw.get("borrowed", max(0, registered - current)) or 0),
                    "status": status_text,
                }
            )
        return normalized
