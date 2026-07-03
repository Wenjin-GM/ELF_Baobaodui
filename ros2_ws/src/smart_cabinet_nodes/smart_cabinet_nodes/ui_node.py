from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from pathlib import Path

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String

from smart_cabinet_interfaces.srv import RequestInventory, RequestManualFan, RequestOpen


class UiBridgeNode(Node):
    def __init__(self):
        super().__init__("ui_node")
        qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self.summary_count = 0
        self.environment_count = 0
        self.inventory_count = 0
        self.battery_count = 0
        self.auth_count = 0
        self.events_count = 0
        self.last_summary = ""
        self.last_environment = ""
        self.last_inventory = ""
        self.last_battery = ""

        self.create_subscription(String, "/ui/summary", self._summary_cb, qos)
        self.create_subscription(String, "/ui/environment", self._environment_cb, qos)
        self.create_subscription(String, "/ui/inventory", self._inventory_cb, qos)
        self.create_subscription(String, "/ui/battery", self._battery_cb, qos)
        self.create_subscription(String, "/ui/auth", self._auth_cb, qos)
        self.create_subscription(String, "/ui/events", self._events_cb, 50)

        self.open_client = self.create_client(RequestOpen, "/cabinet/request_open")
        self.inventory_client = self.create_client(RequestInventory, "/cabinet/request_inventory")
        self.fan_client = self.create_client(RequestManualFan, "/cabinet/request_manual_fan")
        self.get_logger().info("ui_node bridge started")

    def _summary_cb(self, msg: String):
        self.summary_count += 1
        self.last_summary = msg.data

    def _environment_cb(self, msg: String):
        self.environment_count += 1
        self.last_environment = msg.data

    def _inventory_cb(self, msg: String):
        self.inventory_count += 1
        self.last_inventory = msg.data

    def _battery_cb(self, msg: String):
        self.battery_count += 1
        self.last_battery = msg.data

    def _auth_cb(self, msg: String):
        self.auth_count += 1

    def _events_cb(self, msg: String):
        self.events_count += 1
        self.get_logger().info(f"ui event: {msg.data}")

    def request_inventory(self, reason: str = "ui_node_test") -> bool:
        if not self.inventory_client.wait_for_service(timeout_sec=2.0):
            self.get_logger().warning("/cabinet/request_inventory not ready")
            return False
        req = RequestInventory.Request()
        req.reason = reason
        future = self.inventory_client.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=3.0)
        return future.result() is not None and bool(future.result().accepted)

    def request_manual_fan(self, on: bool, reason: str = "ui_node_test") -> bool:
        if not self.fan_client.wait_for_service(timeout_sec=2.0):
            self.get_logger().warning("/cabinet/request_manual_fan not ready")
            return False
        req = RequestManualFan.Request()
        req.on = bool(on)
        req.reason = reason
        future = self.fan_client.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=3.0)
        return future.result() is not None and bool(future.result().accepted)

    def request_open(self, timeout_sec: float = 5.0) -> bool:
        if not self.open_client.wait_for_service(timeout_sec=2.0):
            self.get_logger().warning("/cabinet/request_open not ready")
            return False
        req = RequestOpen.Request()
        req.timeout_sec = float(timeout_sec)
        future = self.open_client.call_async(req)
        rclpy.spin_until_future_complete(self, future, timeout_sec=3.0)
        return future.result() is not None and bool(future.result().accepted)


def run_bridge(args):
    rclpy.init(args=None)
    node = UiBridgeNode()
    try:
        if args.test:
            deadline = time.monotonic() + float(args.test_timeout_sec)
            while time.monotonic() < deadline and (
                node.summary_count < 1
                or node.environment_count < 1
                or node.inventory_count < 1
                or node.battery_count < 1
            ):
                rclpy.spin_once(node, timeout_sec=0.1)
            if args.request_inventory:
                accepted = node.request_inventory("ui_node_test")
                node.get_logger().info(f"request_inventory accepted={accepted}")
                end = time.monotonic() + 3.0
                while time.monotonic() < end:
                    rclpy.spin_once(node, timeout_sec=0.1)
            if args.request_open:
                accepted = node.request_open(timeout_sec=float(args.request_open_timeout))
                node.get_logger().info(f"request_open accepted={accepted}")
                end = time.monotonic() + 3.0
                while time.monotonic() < end:
                    rclpy.spin_once(node, timeout_sec=0.1)
            if args.request_fan_on:
                accepted = node.request_manual_fan(True, "ui_node_test")
                node.get_logger().info(f"request_manual_fan(on) accepted={accepted}")
                end = time.monotonic() + 2.0
                while time.monotonic() < end:
                    rclpy.spin_once(node, timeout_sec=0.1)
            if args.request_fan_off:
                accepted = node.request_manual_fan(False, "ui_node_test")
                node.get_logger().info(f"request_manual_fan(off) accepted={accepted}")
                end = time.monotonic() + 2.0
                while time.monotonic() < end:
                    rclpy.spin_once(node, timeout_sec=0.1)
            print(
                "UI_NODE_TEST "
                f"summary={node.summary_count} "
                f"environment={node.environment_count} "
                f"inventory={node.inventory_count} "
                f"battery={node.battery_count} "
                f"auth={node.auth_count} "
                f"events={node.events_count}"
            )
            return 0
        try:
            rclpy.spin(node)
        except (KeyboardInterrupt, ExternalShutdownException):
            pass
        return 0
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


def run_window(args):
    show_dir = Path(args.show_dir).expanduser().resolve()
    sys.path.insert(0, str(show_dir))
    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtWidgets import QApplication
    from main_window import MainWindow
    from ros_backend import RosBackend

    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "0")
    os.environ.setdefault("QT_SCALE_FACTOR", "1")
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, False)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv[:1])
    backend = RosBackend()
    window = MainWindow(backend=backend)
    app.aboutToQuit.connect(backend.stop)

    def target_screen():
        preferred_name = os.environ.get("SMART_CABINET_UI_SCREEN", "").strip()
        screens = app.screens()
        if preferred_name:
            for screen in screens:
                if preferred_name in screen.name():
                    return screen
        return app.primaryScreen()

    screen = target_screen()
    screen_geometry = screen.geometry()

    def write_ui_diag():
        text = (
            f"[UI-DIAG] windowed={args.windowed} "
            f"isFullScreen={window.isFullScreen()} "
            f"targetScreen={screen.name()} "
            f"target={screen_geometry.getRect()} "
            f"primary={app.primaryScreen().name()} "
            f"screen={app.primaryScreen().geometry().getRect()} "
            f"available={app.primaryScreen().availableGeometry().getRect()} "
            f"window={window.geometry().getRect()} "
            f"frame={window.frameGeometry().getRect()}"
        )
        print(text, flush=True)
        try:
            diag_path = Path(os.environ.get("SMART_CABINET_UI_DIAG", "/tmp/smart_cabinet_ui_diag.txt"))
            diag_path.write_text(text + "\n", encoding="utf-8")
        except Exception as exc:
            print(f"[UI-DIAG] failed to write diag: {exc}", flush=True)

    def quit_from_signal(signum, _frame):
        print(f"ui_node received signal {signum}, exiting...")
        app.quit()

    signal.signal(signal.SIGINT, quit_from_signal)
    signal.signal(signal.SIGTERM, quit_from_signal)

    signal_timer = QTimer()
    signal_timer.start(200)
    signal_timer.timeout.connect(lambda: None)

    if args.windowed:
        window.resize(screen_geometry.width(), screen_geometry.height())
        window.move(screen_geometry.topLeft())
        window.show()
    else:
        # On the ELF dual-display setup, native showFullScreen() may use the
        # primary HDMI height even after moving to DSI. Use an exact frameless
        # 1024x600 window on the selected DSI screen by default.
        if os.environ.get("SMART_CABINET_UI_NATIVE_FULLSCREEN", "0") in {"1", "true", "yes", "on"}:
            window.setGeometry(screen_geometry)
            window.move(screen_geometry.topLeft())
            window.showFullScreen()
            if window.windowHandle():
                window.windowHandle().setScreen(screen)
            QTimer.singleShot(100, lambda: (window.setGeometry(screen_geometry), window.move(screen_geometry.topLeft()), window.showFullScreen()))
            QTimer.singleShot(500, lambda: (
                window.windowHandle().setScreen(screen) if window.windowHandle() else None,
                window.setGeometry(screen_geometry),
                window.move(screen_geometry.topLeft()),
                window.showFullScreen(),
                window.raise_(),
                window.activateWindow(),
            ))
        else:
            window.setWindowFlags(
                window.windowFlags()
                | Qt.FramelessWindowHint
                | Qt.WindowStaysOnTopHint
                | Qt.X11BypassWindowManagerHint
            )
            window.setFixedSize(screen_geometry.width(), screen_geometry.height())
            window.setGeometry(screen_geometry)
            window.move(screen_geometry.topLeft())
            window.show()
            QTimer.singleShot(100, lambda: (window.setFixedSize(screen_geometry.width(), screen_geometry.height()), window.setGeometry(screen_geometry), window.move(screen_geometry.topLeft()), window.raise_(), window.activateWindow()))
            QTimer.singleShot(500, lambda: (window.setFixedSize(screen_geometry.width(), screen_geometry.height()), window.setGeometry(screen_geometry), window.move(screen_geometry.topLeft()), window.raise_(), window.activateWindow()))
        # Diagnostic: print geometry after event loop starts.
        QTimer.singleShot(1000, write_ui_diag)

    try:
        return app.exec_()
    except KeyboardInterrupt:
        app.quit()
        return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Smart cabinet UI ROS node")
    parser.add_argument("--bridge-only", action="store_true", help="Run subscriptions/services without PyQt window")
    parser.add_argument("--test", action="store_true", help="Bridge smoke test and exit")
    parser.add_argument("--request-inventory", action="store_true", help="Request mock/real inventory during --test")
    parser.add_argument("--request-open", action="store_true", help="Call /cabinet/request_open during --test")
    parser.add_argument("--request-open-timeout", type=float, default=5.0)
    parser.add_argument("--request-fan-on", action="store_true", help="Call /cabinet/request_manual_fan(on) during --test")
    parser.add_argument("--request-fan-off", action="store_true", help="Call /cabinet/request_manual_fan(off) during --test")
    parser.add_argument("--test-timeout-sec", type=float, default=5.0)
    parser.add_argument("--show-dir", default=os.environ.get("SMART_CABINET_SHOW_DIR", "~/smart_tool_cabinet/show/Script"))
    parser.add_argument("--windowed", action="store_true", help="Run the PyQt UI in a normal window instead of fullscreen")
    args = parser.parse_args(argv)

    if args.bridge_only or args.test:
        return run_bridge(args)
    return run_window(args)


if __name__ == "__main__":
    raise SystemExit(main())
