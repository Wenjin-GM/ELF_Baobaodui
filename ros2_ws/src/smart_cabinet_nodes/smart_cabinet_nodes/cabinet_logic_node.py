from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict

import rclpy
from rclpy.action import ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String
from std_srvs.srv import Trigger

from smart_cabinet_interfaces.action import AuthenticateFace, ReadNfcCard, RunInventory
from smart_cabinet_interfaces.srv import (
    Beep,
    OpenLock,
    RequestInventory,
    RequestManualFan,
    RequestOpen,
    RequestTempUnlock,
    SetFan,
)

from .common import DATA_DIR, ensure_data_dirs, json_text, now_iso, write_json_record


class CabinetLogicNode(Node):
    AUTHED_STATES = {"USER_AUTHED", "ADMIN_AUTHED", "MAINTENANCE"}

    def __init__(self):
        super().__init__("cabinet_logic_node")
        self.callback_group = ReentrantCallbackGroup()
        self.declare_parameter("auth_timeout_sec", 5.0)
        self.declare_parameter("face_min_confidence", 0.45)
        self.declare_parameter("humidity_on", 55.0)
        self.declare_parameter("humidity_off", 50.0)
        self.declare_parameter("temp_on", 35.0)
        self.declare_parameter("temp_off", 30.0)
        self.declare_parameter("lock_pulse_sec", 0.3)
        self.declare_parameter("simulate_missing_battery", True)
        self.declare_parameter("simulate_missing_vision", True)
        self.declare_parameter("record_runtime_data", True)

        self.state = "STANDBY"
        self.current_user: Dict[str, Any] | None = None
        self.last_env: Dict[str, Any] = {}
        self.last_battery: Dict[str, Any] = {}
        self.last_actuator: Dict[str, Any] = {}
        self.last_inventory: Dict[str, Any] = {}
        self.last_inventory_image: str = ""
        self.last_auth: Dict[str, Any] = {}
        self.fan_auto_on = False
        self.summary_seq = 0
        self.mock_battery_tick = 0
        self.mock_inventory_tick = 0
        ensure_data_dirs()

        ui_qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )

        self.pub_state = self.create_publisher(String, "/cabinet/state", ui_qos)
        self.pub_events = self.create_publisher(String, "/cabinet/events", 50)
        self.pub_auth = self.create_publisher(String, "/auth/result", 10)
        self.pub_ui_summary = self.create_publisher(String, "/ui/summary", ui_qos)
        self.pub_ui_environment = self.create_publisher(String, "/ui/environment", ui_qos)
        self.pub_ui_inventory = self.create_publisher(String, "/ui/inventory", ui_qos)
        self.pub_ui_inventory_image = self.create_publisher(String, "/ui/inventory_image", ui_qos)
        self.pub_ui_battery = self.create_publisher(String, "/ui/battery", ui_qos)
        self.pub_ui_auth = self.create_publisher(String, "/ui/auth", ui_qos)
        self.pub_ui_events = self.create_publisher(String, "/ui/events", 50)

        self.sub_env = self.create_subscription(String, "/env/state", self.on_env, 10)
        self.sub_battery = self.create_subscription(String, "/battery/state", self.on_battery, 10)
        self.sub_actuator = self.create_subscription(String, "/actuator/state", self.on_actuator, 10)
        self.sub_inventory_result = self.create_subscription(String, "/vision/inventory_result", self.on_inventory_result, 10)
        self.sub_inventory_image = self.create_subscription(String, "/vision/inventory_image", self.on_inventory_image, 10)

        self.nfc_client = ActionClient(self, ReadNfcCard, "/auth/read_nfc_card", callback_group=self.callback_group)
        self.face_client = ActionClient(self, AuthenticateFace, "/auth/authenticate_face", callback_group=self.callback_group)
        self.vision_client = ActionClient(self, RunInventory, "/vision/run_inventory", callback_group=self.callback_group)
        self.open_lock_client = self.create_client(OpenLock, "/actuator/open_lock", callback_group=self.callback_group)
        self.set_fan_client = self.create_client(SetFan, "/actuator/set_fan", callback_group=self.callback_group)
        self.beep_client = self.create_client(Beep, "/actuator/beep", callback_group=self.callback_group)

        self.create_service(RequestOpen, "/cabinet/request_open", self.request_open, callback_group=self.callback_group)
        self.create_service(RequestInventory, "/cabinet/request_inventory", self.request_inventory, callback_group=self.callback_group)
        self.create_service(RequestManualFan, "/cabinet/request_manual_fan", self.request_manual_fan, callback_group=self.callback_group)
        self.create_service(RequestTempUnlock, "/cabinet/request_temp_unlock", self.request_temp_unlock, callback_group=self.callback_group)
        self.create_service(Trigger, "/cabinet/logout", self.request_logout, callback_group=self.callback_group)

        self.ui_timer = self.create_timer(1.0, self.publish_all_ui)
        self.publish_state()
        self.add_event("系统", "cabinet_logic_node 已启动", "info")

    def run_soon(self, target, *args, delay_sec: float = 0.05):
        timer = threading.Timer(delay_sec, target, args=args)
        timer.daemon = True
        timer.start()

    def parse_json(self, msg: String) -> Dict[str, Any]:
        try:
            return json.loads(msg.data)
        except Exception as exc:
            self.get_logger().warning(f"invalid JSON topic: {exc}")
            return {}

    def set_state(self, state: str):
        if self.state == state:
            return
        old = self.state
        self.state = state
        self.add_event("状态", f"{old} -> {state}", "info")
        self.publish_state()
        self.publish_all_ui()

    def _prev_auth_state(self) -> str:
        """Return the authenticated state the user was in before an
        operation (inventory, etc.), or STANDBY if no user is logged in."""
        if self.current_user and self.current_user.get("name"):
            role = self.current_user.get("role", "user")
            return "ADMIN_AUTHED" if role == "admin" else "USER_AUTHED"
        return "STANDBY"

    def publish_state(self):
        payload = {
            "state": self.state,
            "current_user": self.current_user,
            "timestamp": now_iso(),
        }
        self.pub_state.publish(String(data=json_text(payload)))

    def add_event(self, event_type: str, content: str, level: str = "info"):
        payload = {
            "type": event_type,
            "content": content,
            "level": level,
            "timestamp": now_iso(),
        }
        text = json_text(payload)
        self.pub_events.publish(String(data=text))
        self.pub_ui_events.publish(String(data=text))
        self.record_data("events", payload, "event")
        self.get_logger().info(f"[{event_type}] {content}")

    def on_env(self, msg: String):
        self.last_env = self.parse_json(msg)
        self.record_data("environment", self.last_env, "env")
        self.handle_env_control()
        self.publish_ui_environment()
        self.publish_ui_summary()

    def on_battery(self, msg: String):
        self.last_battery = self.parse_json(msg)
        self.record_data("battery", self.last_battery, "battery")
        self.publish_ui_battery()
        self.publish_ui_summary()

    def on_actuator(self, msg: String):
        self.last_actuator = self.parse_json(msg)
        self.record_data("actuator", self.last_actuator, "actuator")
        self.publish_ui_environment()
        self.publish_ui_summary()

    def on_inventory_result(self, msg: String):
        self.last_inventory = self.parse_json(msg)
        self.record_inventory_result(self.last_inventory)
        self.publish_ui_inventory()
        self.publish_ui_summary()

    def on_inventory_image(self, msg: String):
        self.last_inventory_image = msg.data
        self.pub_ui_inventory_image.publish(String(data=msg.data))

    def handle_env_control(self):
        if not self.last_env.get("valid", False):
            return
        humidity = float(self.last_env.get("humidity", 0.0))
        temp = float(self.last_env.get("temperature", 0.0))
        humidity_on = float(self.get_parameter("humidity_on").value)
        humidity_off = float(self.get_parameter("humidity_off").value)
        temp_on = float(self.get_parameter("temp_on").value)
        temp_off = float(self.get_parameter("temp_off").value)

        if not self.fan_auto_on and (humidity > humidity_on or temp > temp_on):
            self.call_set_fan(True, "auto_env_control")
            self.fan_auto_on = True
            self.add_event("环境", f"温湿度超限，启动风扇 T={temp:.1f}, H={humidity:.1f}", "warning")
        elif self.fan_auto_on and humidity <= humidity_off and temp <= temp_off:
            self.call_set_fan(False, "auto_env_recovered")
            self.fan_auto_on = False
            self.add_event("环境", f"环境恢复，关闭风扇 T={temp:.1f}, H={humidity:.1f}", "info")

    def call_set_fan(self, on: bool, reason: str):
        if not self.set_fan_client.service_is_ready():
            self.get_logger().warning("/actuator/set_fan not ready")
            return
        req = SetFan.Request()
        req.on = bool(on)
        req.reason = reason
        self.set_fan_client.call_async(req)

    def request_open(self, request, response):
        self.add_event("ui", f"request_open received, timeout={float(request.timeout_sec):.1f}s", "info")
        if self.state in {"USER_AUTHED", "ADMIN_AUTHED"}:
            response.accepted = True
            response.message = "already authenticated; opening lock"
            self.run_soon(self.open_lock_worker, "authenticated_request")
            return response
        if self.state != "STANDBY":
            response.accepted = False
            response.message = f"request_open refused in state {self.state}"
            self.add_event("ui", response.message, "warning")
            return response
        timeout = float(request.timeout_sec) if request.timeout_sec > 0 else float(self.get_parameter("auth_timeout_sec").value)
        self.set_state("AUTH_PENDING")
        response.accepted = True
        response.message = "authentication started"
        self.run_soon(self.auth_and_open_worker, timeout)
        return response

    def auth_and_open_worker(self, timeout: float):
        auth_result = self.try_auth(timeout)
        if not auth_result.get("success"):
            if self.state != "AUTH_PENDING":
                return
            self.current_user = None
            self.last_auth = auth_result
            self.publish_auth(auth_result)
            self.add_event("认证", auth_result.get("message", "认证失败"), "warning")
            self.set_state("STANDBY")
            return

        self.apply_auth_success(auth_result, "auth_success")

    def apply_auth_success(self, auth_result: Dict[str, Any], reason: str):
        if self.state in {"USER_AUTHED", "ADMIN_AUTHED"} and self.current_user:
            return
        auth_result.setdefault("method", "NFC")
        if not auth_result.get("user_name"):
            auth_result["user_name"] = auth_result.get("name", "")
        if not auth_result.get("role"):
            auth_result["role"] = "user"
        self.current_user = {
            "name": auth_result.get("user_name", ""),
            "role": auth_result.get("role", "user"),
            "method": auth_result.get("method", ""),
        }
        auth_result["current_user"] = self.current_user
        self.last_auth = auth_result
        self.publish_auth(auth_result)
        self.set_state("ADMIN_AUTHED" if self.current_user["role"] == "admin" else "USER_AUTHED")
        self.add_event("认证", f"{self.current_user['name']} 通过 {self.current_user['method']} 认证", "info")
        self.open_lock_worker(reason)

    def open_lock_worker(self, reason: str):
        if self.call_open_lock():
            self.add_event("开柜", f"门锁已打开 ({reason})", "info")
        else:
            self.add_event("开柜", "门锁打开失败", "warning")
        self.publish_all_ui()

    def try_auth(self, timeout: float) -> Dict[str, Any]:
        deadline = time.monotonic() + timeout
        results = []

        nfc_result = self.call_nfc_action(timeout)
        if nfc_result.get("success") and nfc_result.get("authorized"):
            nfc_result["method"] = "NFC"
            return nfc_result
        results.append(nfc_result)

        remaining = max(0.1, deadline - time.monotonic())
        face_result = self.call_face_action(remaining)
        if face_result.get("success"):
            face_result["method"] = "人脸识别"
            return face_result
        results.append(face_result)

        return {
            "success": False,
            "authorized": False,
            "message": "; ".join(item.get("message", "failed") for item in results if item),
            "timestamp": now_iso(),
        }

    def call_nfc_action(self, timeout: float) -> Dict[str, Any]:
        if not self.nfc_client.wait_for_server(timeout_sec=0.2):
            return {"success": False, "message": "NFC action server not ready"}
        goal = ReadNfcCard.Goal()
        goal.timeout_sec = float(timeout)
        future = self.nfc_client.send_goal_async(goal)
        goal_handle = self.wait_for_future(future, timeout + 1.0)
        if goal_handle is None or not goal_handle.accepted:
            return {"success": False, "message": "NFC goal rejected"}
        result_future = goal_handle.get_result_async()
        result_msg = self.wait_for_future(result_future, timeout + 1.0)
        if result_msg is None:
            return {"success": False, "message": "NFC result timeout"}
        result = result_msg.result
        return {
            "success": bool(result.success),
            "uid": result.uid,
            "authorized": bool(result.authorized),
            "user_name": result.user_name,
            "role": result.role,
            "message": result.message,
            "timestamp": now_iso(),
        }

    def call_face_action(self, timeout: float) -> Dict[str, Any]:
        if not self.face_client.wait_for_server(timeout_sec=0.2):
            return {"success": False, "message": "face action server not ready"}
        goal = AuthenticateFace.Goal()
        goal.timeout_sec = float(timeout)
        goal.min_confidence = float(self.get_parameter("face_min_confidence").value)
        future = self.face_client.send_goal_async(goal)
        goal_handle = self.wait_for_future(future, timeout + 1.0)
        if goal_handle is None or not goal_handle.accepted:
            return {"success": False, "message": "face goal rejected"}
        result_future = goal_handle.get_result_async()
        result_msg = self.wait_for_future(result_future, timeout + 1.0)
        if result_msg is None:
            return {"success": False, "message": "face result timeout"}
        result = result_msg.result
        return {
            "success": bool(result.success),
            "user_name": result.user_name,
            "role": result.role,
            "confidence": float(result.confidence),
            "message": result.message,
            "timestamp": now_iso(),
        }

    def call_open_lock(self) -> bool:
        if not self.open_lock_client.wait_for_service(timeout_sec=1.0):
            return False
        req = OpenLock.Request()
        req.pulse_sec = float(self.get_parameter("lock_pulse_sec").value)
        future = self.open_lock_client.call_async(req)
        result = self.wait_for_future(future, 2.0)
        return result is not None and bool(result.success)

    def wait_for_future(self, future, timeout_sec: float):
        done = threading.Event()
        future.add_done_callback(lambda _future: done.set())
        if not done.wait(max(0.1, float(timeout_sec))):
            return None
        try:
            return future.result()
        except Exception as exc:
            self.get_logger().warning(f"future failed: {exc}")
            return None

    def publish_auth(self, data: Dict[str, Any]):
        if self.current_user:
            data.setdefault("user_name", self.current_user.get("name", ""))
            data.setdefault("role", self.current_user.get("role", "user"))
            data.setdefault("method", self.current_user.get("method", ""))
            data.setdefault("current_user", self.current_user)
        text = json_text(data)
        self.pub_auth.publish(String(data=text))
        self.pub_ui_auth.publish(String(data=text))
        self.record_data("auth", data, "auth")
        self.publish_ui_summary()

    def request_inventory(self, request, response):
        reason = request.reason or "user_request"
        self.add_event("ui", f"request_inventory received: {reason}", "info")
        if self.state not in self.AUTHED_STATES and self.state != "CABINET_OPEN":
            response.accepted = False
            response.message = f"request_inventory requires authenticated state, current={self.state}"
            self.add_event("ui", response.message, "warning")
            return response
        response.accepted = True
        response.message = "inventory requested"
        self.run_soon(self.inventory_worker, reason)
        return response

    def inventory_worker(self, reason: str):
        self.set_state("CHECKING_AFTER_CLOSE")
        if not self.vision_client.wait_for_server(timeout_sec=0.5):
            if bool(self.get_parameter("simulate_missing_vision").value):
                self.add_event("inventory", "vision_node offline; using mock inventory result", "info")
                self.apply_mock_inventory(reason)
                self.set_state(self._prev_auth_state())
                return
            self.add_event("盘点", "vision_node 未上线，无法盘点", "warning")
            self.set_state("ALARM_ACTIVE")
            return
        goal = RunInventory.Goal()
        goal.reason = reason
        goal.save_image = True
        future = self.vision_client.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, future, timeout_sec=2.0)
        goal_handle = future.result()
        if goal_handle is None or not goal_handle.accepted:
            self.add_event("盘点", "视觉盘点请求被拒绝", "warning")
            self.set_state("ALARM_ACTIVE")
            return
        result_future = goal_handle.get_result_async()
        rclpy.spin_until_future_complete(self, result_future, timeout_sec=20.0)
        if result_future.result() is None:
            self.add_event("盘点", "视觉盘点超时", "warning")
            self.set_state("ALARM_ACTIVE")
            return
        result = result_future.result().result
        self.last_inventory = {
            "success": result.success,
            "image_path": result.image_path,
            "is_normal": result.is_normal,
            "zones": json.loads(result.zones_json or "[]"),
            "detections": json.loads(result.detections_json or "[]"),
            "message": result.message,
            "timestamp": now_iso(),
        }
        self.record_inventory_result(self.last_inventory)
        self.publish_ui_inventory()
        if result.success and result.is_normal:
            self.add_event("盘点", "盘点正常", "info")
            self.set_state(self._prev_auth_state())
        else:
            self.add_event("盘点", f"盘点异常: {result.message}", "warning")
            self.call_beep()
            self.set_state("ALARM_ACTIVE")

    def call_beep(self):
        if not self.beep_client.wait_for_service(timeout_sec=0.5):
            return
        req = Beep.Request()
        req.times = 3
        req.on_sec = 0.15
        req.off_sec = 0.15
        self.beep_client.call_async(req)

    def request_manual_fan(self, request, response):
        if self.state not in self.AUTHED_STATES:
            response.accepted = False
            response.message = f"manual fan requires authenticated state, current={self.state}"
            self.add_event("ui", response.message, "warning")
            return response
        self.call_set_fan(bool(request.on), request.reason or "manual")
        self.add_event("ui", f"request_manual_fan received: {'on' if request.on else 'off'} ({request.reason or 'manual'})", "info")
        response.accepted = True
        response.message = f"manual fan {'on' if request.on else 'off'} requested"
        return response

    def request_temp_unlock(self, request, response):
        if self.state not in {"ADMIN_AUTHED", "MAINTENANCE"}:
            response.accepted = False
            response.message = "temp unlock requires admin or maintenance state"
            self.add_event("ui", response.message, "warning")
            return response
        ok = self.call_open_lock()
        response.accepted = ok
        response.message = "temp unlock done" if ok else "temp unlock failed"
        self.add_event("开柜", response.message, "info" if ok else "warning")
        return response

    def request_logout(self, _request, response):
        user_name = (self.current_user or {}).get("name", "-")
        self.current_user = None
        self.last_auth = {}
        self.set_state("STANDBY")
        self.add_event("认证", f"{user_name} 已退出登录", "info")
        response.success = True
        response.message = "logged out"
        self.publish_all_ui()
        return response

    def publish_all_ui(self):
        try:
            self.publish_state()
            self.publish_ui_environment()
            self.publish_ui_battery()
            self.publish_ui_inventory()
            self.publish_ui_summary()
            if self.last_auth:
                self.pub_ui_auth.publish(String(data=json_text(self.last_auth)))
        except Exception as exc:
            self.get_logger().error(f"publish_all_ui failed: {exc}")

    def publish_ui_summary(self):
        try:
            self.summary_seq += 1
            payload = {
                "seq": self.summary_seq,
                "state": self.state,
                "authenticated": self.state in self.AUTHED_STATES and bool(self.current_user),
                "current_user": self.current_user or {},
                "environment": self.last_env or {},
                "battery": self.last_battery or {},
                "actuator": self.last_actuator or {},
                "inventory": self.last_inventory or {},
                "auth": self.last_auth or {},
                "timestamp": now_iso(),
            }
            self.pub_ui_summary.publish(String(data=json_text(payload)))
        except Exception as exc:
            self.get_logger().error(f"publish_ui_summary failed: {exc}")

    def publish_ui_environment(self):
        payload = {
            "temperature": self.last_env.get("temperature"),
            "humidity": self.last_env.get("humidity"),
            "valid": self.last_env.get("valid", False),
            "fan_on": self.last_actuator.get("fan_on", self.fan_auto_on),
            "alarm_on": self.state == "ALARM_ACTIVE",
            "timestamp": now_iso(),
        }
        self.pub_ui_environment.publish(String(data=json_text(payload)))

    def publish_ui_battery(self):
        if not self.last_battery and bool(self.get_parameter("simulate_missing_battery").value):
            self.last_battery = self.build_mock_battery()
            self.record_data("battery", self.last_battery, "mock_battery")
        self.pub_ui_battery.publish(String(data=json_text(self.last_battery or {"module_online": False, "timestamp": now_iso()})))

    def publish_ui_inventory(self):
        payload = self.last_inventory or {
            "success": False,
            "is_normal": True,
            "zones": [],
            "detections": [],
            "message": "no inventory result yet",
            "timestamp": now_iso(),
        }
        self.pub_ui_inventory.publish(String(data=json_text(payload)))

    def build_mock_battery(self) -> Dict[str, Any]:
        self.mock_battery_tick += 1
        slots = [True, self.mock_battery_tick % 4 != 0, True, self.mock_battery_tick % 6 != 0]
        return {
            "module_online": True,
            "status_valid": True,
            "box_present": any(slots),
            "relay_on": any(slots),
            "slots": slots,
            "battery_levels": [92, 0 if not slots[1] else 78, 86, 0 if not slots[3] else 64],
            "source": "cabinet_logic_mock",
            "timestamp": now_iso(),
        }

    def build_mock_inventory(self, reason: str) -> Dict[str, Any]:
        self.mock_inventory_tick += 1
        missing = self.mock_inventory_tick % 5 == 0
        zones = [
            {"zone_id": 1, "zone_name": "battery_box_zone", "registered": 1, "current": 1, "borrowed": 0, "status": "normal"},
            {"zone_id": 2, "zone_name": "pliers_zone", "registered": 2, "current": 1 if missing else 2, "borrowed": 1 if missing else 0, "status": "missing" if missing else "normal"},
            {"zone_id": 3, "zone_name": "thermometer_zone", "registered": 2, "current": 2, "borrowed": 0, "status": "normal"},
            {"zone_id": 4, "zone_name": "multimeter_zone", "registered": 2, "current": 2, "borrowed": 0, "status": "normal"},
            {"zone_id": 5, "zone_name": "glove_zone", "registered": 2, "current": 2, "borrowed": 0, "status": "normal"},
        ]
        return {
            "success": True,
            "is_normal": not missing,
            "zones": zones,
            "detections": [],
            "image_path": "",
            "reason": reason,
            "source": "cabinet_logic_mock",
            "message": "mock inventory normal" if not missing else "mock inventory: zone 2 missing one item",
            "timestamp": now_iso(),
        }

    def apply_mock_inventory(self, reason: str):
        self.last_inventory = self.build_mock_inventory(reason)
        self.record_inventory_result(self.last_inventory)
        self.publish_ui_inventory()
        self.publish_ui_summary()
        self.pub_ui_inventory_image.publish(String(data=self.last_inventory.get("image_path", "")))

    def record_enabled(self) -> bool:
        return bool(self.get_parameter("record_runtime_data").value)

    def record_data(self, category: str, data: Dict[str, Any], prefix: str):
        if not self.record_enabled() or not data:
            return
        try:
            write_json_record(category, data, prefix)
        except Exception as exc:
            self.get_logger().warning(f"record {category} failed: {exc}")

    def record_inventory_result(self, data: Dict[str, Any]):
        if not self.record_enabled() or not data:
            return
        try:
            path = write_json_record("inventory_result", data, "inventory")
            data.setdefault("result_path", str(path))
            if not data.get("image_path"):
                data["image_dir"] = str(DATA_DIR / "inventory_images")
        except Exception as exc:
            self.get_logger().warning(f"record inventory failed: {exc}")


def main(args=None):
    rclpy.init(args=args)
    node = CabinetLogicNode()
    executor = MultiThreadedExecutor(num_threads=4)
    try:
        rclpy.spin(node, executor=executor)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
