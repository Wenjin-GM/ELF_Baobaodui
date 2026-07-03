from __future__ import annotations

import threading
import time
import os

import rclpy
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node

from smart_cabinet_interfaces.action import ReadNfcCard

from .common import ensure_project_imports, load_authorized_cards, role_for_card


class NfcNode(Node):
    def __init__(self):
        super().__init__("nfc_node")
        self.lock_fd = None
        self.acquire_process_lock()
        self.declare_parameter("bus", 7)
        self.declare_parameter("address", 0x24)
        self.declare_parameter("poll_sec", 0.1)
        self.declare_parameter("dry_run", False)
        self.declare_parameter("debug", False)
        self.declare_parameter("open_retries", 3)
        self.declare_parameter("open_retry_delay_sec", 0.25)
        self.declare_parameter("authorized_cards_path", "")

        self.dry_run = bool(self.get_parameter("dry_run").value)
        self.nfc = None
        self.driver_cls = None
        self.last_error = ""
        self.bus = int(self.get_parameter("bus").value)
        self.address = int(self.get_parameter("address").value)
        self.io_lock = threading.Lock()
        if not self.dry_run:
            ensure_project_imports()
            from PN532.drivers.i2c_pn532 import PN532_I2C

            self.driver_cls = PN532_I2C
            self.get_logger().info(
                f"NFC action server ready; PN532 will be opened on demand at i2c-{self.bus}, addr=0x{self.address:02X}"
            )
        else:
            self.get_logger().info("dry_run enabled; NFC action will return mock failure unless mock_uid is set")
            self.declare_parameter("mock_uid", "")

        self.action_server = ActionServer(
            self,
            ReadNfcCard,
            "/auth/read_nfc_card",
            execute_callback=self.execute,
            goal_callback=self.goal_callback,
            cancel_callback=self.cancel_callback,
        )

    def acquire_process_lock(self) -> None:
        """Prevent two nfc_node processes from contending for one PN532 bus."""
        if os.name != "posix":
            return
        try:
            import fcntl

            fd = os.open("/tmp/smart_cabinet_nfc_node.lock", os.O_RDWR | os.O_CREAT, 0o644)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                os.close(fd)
                self.get_logger().error(
                    "another nfc_node process is already running; refusing to start a second NFC owner"
                )
                raise RuntimeError("nfc_node already running") from exc
            os.ftruncate(fd, 0)
            os.write(fd, str(os.getpid()).encode("ascii"))
            self.lock_fd = fd
        except RuntimeError:
            raise
        except Exception as exc:
            self.get_logger().warning(f"could not create nfc_node process lock: {exc}")

    def goal_callback(self, goal_request):
        if goal_request.timeout_sec <= 0:
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def cancel_callback(self, goal_handle):
        return CancelResponse.ACCEPT

    def execute(self, goal_handle):
        timeout = max(0.1, float(goal_handle.request.timeout_sec))
        poll_sec = max(0.05, float(self.get_parameter("poll_sec").value))
        deadline = time.monotonic() + timeout
        feedback = ReadNfcCard.Feedback()
        result = ReadNfcCard.Result()

        try:
            self.last_error = ""
            self.get_logger().info(f"NFC auth action started, timeout={timeout:.1f}s")
            if not self.dry_run and not self.open_reader():
                result.success = False
                result.uid = ""
                result.authorized = False
                result.user_name = ""
                result.role = ""
                result.message = self.last_error or "PN532 offline"
                goal_handle.succeed()
                return result

            while time.monotonic() < deadline:
                if goal_handle.is_cancel_requested:
                    goal_handle.canceled()
                    result.success = False
                    result.message = "cancelled"
                    return result

                remaining = max(0.0, deadline - time.monotonic())
                feedback.status = f"waiting_for_card {remaining:.1f}s"
                goal_handle.publish_feedback(feedback)

                uid = self.read_uid(timeout=min(1.0, remaining))
                if uid:
                    cards = load_authorized_cards()
                    card = cards.get(uid)
                    authorized = card is not None
                    result.success = True
                    result.uid = uid
                    result.authorized = authorized
                    result.user_name = card.get("name", "") if card else ""
                    result.role = role_for_card(card) if card else ""
                    result.message = "authorized" if authorized else "card not authorized"
                    self.get_logger().info(f"NFC card read uid={uid}, authorized={authorized}")
                    goal_handle.succeed()
                    return result

                if self.last_error:
                    result.success = False
                    result.uid = ""
                    result.authorized = False
                    result.user_name = ""
                    result.role = ""
                    result.message = self.last_error
                    goal_handle.succeed()
                    return result

                time.sleep(poll_sec)

            result.success = False
            result.uid = ""
            result.authorized = False
            result.user_name = ""
            result.role = ""
            result.message = "timeout"
            self.get_logger().info("NFC auth action timed out without card")
            goal_handle.succeed()
            return result
        finally:
            self.close_reader()

    def open_reader(self) -> bool:
        if self.dry_run:
            return True
        if self.driver_cls is None:
            return False
        retries = max(1, int(self.get_parameter("open_retries").value))
        retry_delay = max(0.0, float(self.get_parameter("open_retry_delay_sec").value))
        debug = bool(self.get_parameter("debug").value)

        for attempt in range(1, retries + 1):
            self.close_reader()
            try:
                self.nfc = self.driver_cls(bus=self.bus, address=self.address, debug=debug)
                ok = bool(self.nfc.begin())
            except Exception as exc:
                self.last_error = f"PN532 open failed: {exc}"
                self.get_logger().warning(
                    f"{self.last_error} (attempt {attempt}/{retries})"
                )
                self.close_reader()
                ok = False

            if ok:
                self.last_error = ""
                self.get_logger().info(
                    f"PN532 opened on i2c-{self.bus}, addr=0x{self.address:02X}"
                )
                return True

            self.close_reader()
            if attempt < retries:
                self.get_logger().warning(
                    f"PN532 open retry {attempt}/{retries} failed; retrying in {retry_delay:.2f}s"
                )
                time.sleep(retry_delay)

        self.last_error = f"PN532 open failed on i2c-{self.bus}, addr=0x{self.address:02X}"
        self.get_logger().error(self.last_error)
        return False

    def close_reader(self):
        if self.nfc is not None:
            try:
                self.nfc.close()
            finally:
                self.nfc = None

    def read_uid(self, timeout: float) -> str:
        with self.io_lock:
            if not self.dry_run and self.nfc is None:
                self.last_error = "PN532 reader is not open"
                return ""
            return self.read_uid_unlocked(timeout)

    def read_uid_unlocked(self, timeout: float) -> str:
        if self.dry_run:
            mock_uid = str(self.get_parameter("mock_uid").value).strip().upper()
            return mock_uid

        if self.nfc is None:
            return ""

        try:
            uid = self.nfc.read_passive_target_id(timeout=timeout)
            if not uid:
                return ""
            return "".join(f"{byte:02X}" for byte in uid)
        except Exception as exc:
            self.last_error = f"PN532 read failed: {exc}"
            self.get_logger().warning(self.last_error)
            self.close_reader()
            return ""

    def destroy_node(self):
        if self.action_server is not None:
            self.action_server.destroy()
        self.close_reader()
        if self.lock_fd is not None:
            try:
                os.close(self.lock_fd)
            finally:
                self.lock_fd = None
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None
    executor = MultiThreadedExecutor()
    try:
        node = NfcNode()
        rclpy.spin(node, executor=executor)
    except RuntimeError as exc:
        print(f"nfc_node startup failed: {exc}")
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
