from __future__ import annotations

import importlib.util
import threading
import time
from pathlib import Path

import cv2
import rclpy
from cv_bridge import CvBridge
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node
from sensor_msgs.msg import Image

from smart_cabinet_interfaces.action import AuthenticateFace

from .common import PROJECT_ROOT, ensure_project_imports


class FaceNode(Node):
    def __init__(self):
        super().__init__("face_node")
        self.declare_parameter("camera", "/dev/video21")
        self.declare_parameter("face_db", str(PROJECT_ROOT / "USB" / "face_auth" / "face_db"))
        self.declare_parameter("min_confidence", 0.45)
        self.declare_parameter("frame_interval_sec", 0.2)
        self.declare_parameter("dry_run", False)
        self.declare_parameter("admin_names", "赵增辉,高莫")
        self.declare_parameter("mock_user_name", "")
        self.declare_parameter("mock_role", "user")
        self.declare_parameter("mock_confidence", 0.9)

        self.dry_run = bool(self.get_parameter("dry_run").value)
        self.admin_names = set(
            n.strip() for n in str(self.get_parameter("admin_names").value).split(",") if n.strip()
        )
        self.recognizer = None
        self.init_error = ""
        if not self.dry_run:
            try:
                ensure_project_imports()
                core_path = PROJECT_ROOT / "USB" / "face_auth" / "face_recognition_core.py"
                spec = importlib.util.spec_from_file_location("face_recognition_core", core_path)
                if spec is None or spec.loader is None:
                    raise RuntimeError(f"cannot load face core: {core_path}")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                self.recognizer = module.FaceRecognizer(face_db_dir=str(self.get_parameter("face_db").value))
                self.get_logger().info("FaceRecognizer ready")
            except Exception as exc:
                self.init_error = str(exc)
                self.get_logger().error(f"FaceRecognizer unavailable: {exc}")
        else:
            self.get_logger().info("dry_run enabled; face action uses mock_user_name")

        # ---- camera ----
        self.cap = None
        self._latest_frame = None
        self._frame_lock = threading.Lock()
        self._capture_running = False
        self._capture_thread = None
        self._preview_timer = None
        self._bridge = CvBridge()
        self.preview_pub = self.create_publisher(Image, "/face/preview", 10)
        self._start_capture()

        # ---- auth action ----
        self.action_server = ActionServer(
            self,
            AuthenticateFace,
            "/auth/authenticate_face",
            execute_callback=self.execute,
            goal_callback=self.goal_callback,
            cancel_callback=self.cancel_callback,
        )

    # ── camera ────────────────────────────────────────────────────────

    def _start_capture(self):
        """Open camera + start capture thread + create preview timer."""
        if self.dry_run or self._capture_running:
            return
        device = str(self.get_parameter("camera").value)
        self.cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
        if not self.cap.isOpened():
            self.get_logger().warn(f"camera {device} not available")
            self.cap.release()
            self.cap = None
            return
        self._capture_running = True
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()
        if self._preview_timer is None:
            fps = 1.0 / max(0.1, float(self.get_parameter("frame_interval_sec").value))
            self._preview_timer = self.create_timer(1.0 / fps, self._publish_preview)
        self.get_logger().info(f"camera capture started on /face/preview")

    def _stop_capture(self):
        """Stop capture thread, join, then release camera."""
        self._capture_running = False
        if self._capture_thread is not None and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=1.0)
            self._capture_thread = None
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    def _capture_loop(self):
        """Dedicated thread — only place that calls self.cap.read()."""
        interval = max(0.02, float(self.get_parameter("frame_interval_sec").value))
        while self._capture_running and self.cap is not None:
            ok, frame = self.cap.read()
            if ok and frame is not None:
                with self._frame_lock:
                    self._latest_frame = frame
            time.sleep(interval)

    def _publish_preview(self):
        """ROS timer callback — publishes latest frame, never touches camera."""
        with self._frame_lock:
            frame = self._latest_frame.copy() if self._latest_frame is not None else None
        if frame is None:
            return
        try:
            msg = self._bridge.cv2_to_imgmsg(frame, encoding="bgr8")
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.header.frame_id = "face_camera"
            self.preview_pub.publish(msg)
        except Exception as exc:
            self.get_logger().warn(f"preview publish error: {exc}")

    # ── action callbacks ──────────────────────────────────────────────

    def goal_callback(self, goal_request):
        if goal_request.timeout_sec <= 0:
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def cancel_callback(self, goal_handle):
        return CancelResponse.ACCEPT

    def execute(self, goal_handle):
        timeout = max(0.1, float(goal_handle.request.timeout_sec))
        min_conf = float(goal_handle.request.min_confidence or self.get_parameter("min_confidence").value)
        deadline = time.monotonic() + timeout
        feedback = AuthenticateFace.Feedback()
        result = AuthenticateFace.Result()

        if self.dry_run:
            name = str(self.get_parameter("mock_user_name").value).strip()
            if name:
                result.success = True
                result.user_name = name
                result.role = str(self.get_parameter("mock_role").value)
                result.confidence = float(self.get_parameter("mock_confidence").value)
                result.message = "mock face authenticated"
                goal_handle.succeed()
                return result
            time.sleep(timeout)
            result.success = False
            result.message = "mock timeout"
            goal_handle.succeed()
            return result

        if self.recognizer is None:
            result.success = False
            result.message = f"face unavailable: {self.init_error or 'not initialized'}"
            goal_handle.succeed()
            return result

        # Use latest frame from preview loop — never read camera directly here
        # to avoid racing with _publish_preview() on the same VideoCapture.
        if self.cap is None or not self._capture_running:
            self._start_capture()
        if self.cap is None or not self._capture_running:
            result.success = False
            result.message = "camera open failed"
            goal_handle.abort()
            return result

        try:
            while time.monotonic() < deadline:
                if goal_handle.is_cancel_requested:
                    goal_handle.canceled()
                    result.success = False
                    result.message = "cancelled"
                    return result

                remaining = max(0.0, deadline - time.monotonic())
                feedback.status = f"recognizing {remaining:.1f}s"
                goal_handle.publish_feedback(feedback)

                with self._frame_lock:
                    frame = self._latest_frame.copy() if self._latest_frame is not None else None
                if frame is not None:
                    face = self.recognizer.detect_face(frame)
                    if face is not None:
                        feat = self.recognizer.extract_feature(face)
                        name, confidence = self.recognizer.recognize(feat)
                        if name and confidence >= min_conf:
                            result.success = True
                            result.user_name = str(name)
                            result.role = "admin" if str(name) in self.admin_names else "user"
                            result.confidence = float(confidence)
                            result.message = "face authenticated"
                            goal_handle.succeed()
                            return result

                time.sleep(float(self.get_parameter("frame_interval_sec").value))
        finally:
            pass  # camera stays open for preview

        result.success = False
        result.message = "timeout"
        goal_handle.succeed()
        return result

    def destroy_node(self):
        self._stop_capture()
        if self.action_server is not None:
            self.action_server.destroy()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = FaceNode()
    executor = MultiThreadedExecutor()
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
