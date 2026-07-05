"""ROS2 cabinet interior inventory node."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Tuple

import cv2
import rclpy
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.executors import ExternalShutdownException, MultiThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import String

from smart_cabinet_interfaces.action import RunInventory

from .common import DATA_DIR, PROJECT_ROOT, ensure_data_dirs, json_text, now_iso, timestamp_name


VISION_INVENTORY_DIR = PROJECT_ROOT / "vision" / "inventory"
if str(VISION_INVENTORY_DIR) not in sys.path:
    sys.path.insert(0, str(VISION_INVENTORY_DIR))

from inventory_core import (  # noqa: E402
    analyze_inventory,
    build_zones_from_detections,
    detections_from_yolo_result,
    expected_counts_from_text,
    load_zones,
    summarize_counts,
    write_zones,
)


def resolve_project_path(value: str, default_relative: str) -> Path:
    raw = value.strip() or default_relative
    path = Path(raw).expanduser()
    if path.is_absolute():
        return path
    candidate = PROJECT_ROOT / path
    if candidate.exists() or candidate.parent.exists():
        return candidate
    return Path.cwd() / path


class VisionNode(Node):
    def __init__(self):
        super().__init__("vision_node")
        self.declare_parameter("device", "/dev/video11")
        self.declare_parameter("fallback_devices", "/dev/video12,/dev/video0")
        self.declare_parameter("model", "vision/best.pt")
        self.declare_parameter("zones", "vision/inventory/zones.json")
        self.declare_parameter("out_dir", "data/inventory_images")
        self.declare_parameter("width", 1920)
        self.declare_parameter("height", 1080)
        self.declare_parameter("warmup", 5)
        self.declare_parameter("imgsz", 960)
        self.declare_parameter("conf", 0.02)
        self.declare_parameter("iou", 0.45)
        self.declare_parameter("dry_run", False)
        self.declare_parameter("calibrate_on_missing_zones", False)
        self.declare_parameter("expected_counts", "")
        self.declare_parameter("zone_expand", 0.35)

        ensure_data_dirs()
        self.pub_result = self.create_publisher(String, "/vision/inventory_result", 10)
        self.pub_image = self.create_publisher(String, "/vision/inventory_image", 10)
        self.model = None
        self.model_error = ""

        if not bool(self.get_parameter("dry_run").value):
            self._load_model()
        else:
            self.get_logger().warning("vision_node dry_run=true; action returns a mock normal result")

        self.action_server = ActionServer(
            self,
            RunInventory,
            "/vision/run_inventory",
            execute_callback=self.execute,
            goal_callback=self.goal_callback,
            cancel_callback=self.cancel_callback,
        )
        self.get_logger().info("vision inventory action server ready: /vision/run_inventory")

    def _load_model(self) -> None:
        model_path = resolve_project_path(str(self.get_parameter("model").value), "vision/best.pt")
        try:
            from ultralytics import YOLO

            if not model_path.exists():
                raise FileNotFoundError(str(model_path))
            self.model = YOLO(str(model_path))
            self.get_logger().info(f"loaded inventory model: {model_path}, names={self.model.names}")
        except Exception as exc:
            self.model_error = f"failed to load inventory model {model_path}: {exc}"
            self.get_logger().error(self.model_error)

    def goal_callback(self, _goal_request):
        return GoalResponse.ACCEPT

    def cancel_callback(self, _goal_handle):
        return CancelResponse.ACCEPT

    def execute(self, goal_handle):
        result = RunInventory.Result()
        feedback = RunInventory.Feedback()
        feedback.status = "starting"
        goal_handle.publish_feedback(feedback)

        try:
            if bool(self.get_parameter("dry_run").value):
                payload = self._mock_payload(goal_handle.request.reason)
            else:
                if self.model is None:
                    result.success = False
                    result.message = self.model_error or "vision model is not loaded"
                    goal_handle.succeed()
                    return result
                payload = self._run_inventory(goal_handle)
        except Exception as exc:
            self.get_logger().error(f"inventory failed: {exc}")
            result.success = False
            result.image_path = ""
            result.is_normal = False
            result.zones_json = "[]"
            result.detections_json = "[]"
            result.message = str(exc)
            self.pub_result.publish(String(data=json_text({
                "success": False,
                "is_normal": False,
                "message": str(exc),
                "timestamp": now_iso(),
            })))
            goal_handle.succeed()
            return result

        result.success = bool(payload.get("success", False))
        result.image_path = str(payload.get("image_path", ""))
        result.is_normal = bool(payload.get("is_normal", False))
        result.zones_json = json.dumps(payload.get("zones", []), ensure_ascii=False)
        result.detections_json = json.dumps(payload.get("detections", []), ensure_ascii=False)
        result.message = str(payload.get("message", ""))
        self.pub_result.publish(String(data=json_text(payload)))
        self.pub_image.publish(String(data=result.image_path))
        goal_handle.succeed()
        return result

    def _run_inventory(self, goal_handle) -> Dict[str, Any]:
        feedback = RunInventory.Feedback()
        feedback.status = "capturing"
        goal_handle.publish_feedback(feedback)

        frame, source_info = self._capture_frame()
        height, width = frame.shape[:2]

        feedback.status = "detecting"
        goal_handle.publish_feedback(feedback)
        prediction = self.model.predict(
            source=frame,
            imgsz=int(self.get_parameter("imgsz").value),
            conf=float(self.get_parameter("conf").value),
            iou=float(self.get_parameter("iou").value),
            verbose=False,
        )[0]
        detections = detections_from_yolo_result(prediction, self.model.names)
        annotated = prediction.plot()

        zones_path = resolve_project_path(str(self.get_parameter("zones").value), "vision/inventory/zones.json")
        if not zones_path.exists():
            if not bool(self.get_parameter("calibrate_on_missing_zones").value):
                raise FileNotFoundError(
                    f"zones config not found: {zones_path}; run inventory_once.py --calibrate-from-current first"
                )
            expected_counts = expected_counts_from_text(str(self.get_parameter("expected_counts").value))
            zones_data = build_zones_from_detections(
                detections,
                image_size=[width, height],
                expected_counts=expected_counts,
                expand_ratio=float(self.get_parameter("zone_expand").value),
            )
            write_zones(zones_path, zones_data)
            self.get_logger().warning(f"zones config missing; calibrated from current image: {zones_path}")
        zones_data = load_zones(zones_path)
        analysis = analyze_inventory(detections, zones_data)

        image_path = ""
        original_image_path = ""
        result_path = ""
        if bool(goal_handle.request.save_image):
            saved = self._save_outputs(frame, annotated, analysis)
            image_path = saved["image_path"]
            original_image_path = saved["original_image_path"]
            result_path = saved["result_path"]

        payload = {
            "success": True,
            "reason": goal_handle.request.reason,
            "source": source_info,
            "model": str(resolve_project_path(str(self.get_parameter("model").value), "vision/best.pt")),
            "zones_path": str(zones_path),
            "image_size": [width, height],
            "counts": summarize_counts(detections),
            "is_normal": analysis["is_normal"],
            "zones": analysis["zones"],
            "detections": analysis["detections"],
            "ignored_detections": analysis.get("ignored_detections", []),
            "unassigned": analysis["unassigned"],
            "message": analysis["message"],
            "image_path": image_path,
            "original_image_path": original_image_path,
            "result_path": result_path,
            "timestamp": now_iso(),
        }
        if result_path:
            Path(result_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.get_logger().info(
            f"inventory done normal={payload['is_normal']} counts={payload['counts']} image={image_path}"
        )
        return payload

    def _capture_frame(self) -> Tuple[Any, Dict[str, Any]]:
        primary_device = str(self.get_parameter("device").value)
        fallback_text = str(self.get_parameter("fallback_devices").value)
        width = int(self.get_parameter("width").value)
        height = int(self.get_parameter("height").value)
        devices = []
        for item in [primary_device, *fallback_text.split(",")]:
            item = item.strip()
            if item and item not in devices:
                devices.append(item)

        errors = []
        for device in devices:
            cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
            try:
                if not cap.isOpened():
                    errors.append(f"{device}: open failed")
                    continue
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                ok, frame = cap.read()
                if not ok or frame is None:
                    errors.append(f"{device}: first read failed")
                    continue
                for _ in range(max(0, int(self.get_parameter("warmup").value) - 1)):
                    next_ok, next_frame = cap.read()
                    if next_ok and next_frame is not None:
                        frame = next_frame
                return frame, {
                    "device": device,
                    "actual_width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                    "actual_height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                }
            finally:
                cap.release()
        raise RuntimeError("camera read failed; tried " + "; ".join(errors))

    def _save_outputs(self, frame, annotated, analysis: Dict[str, Any]) -> Dict[str, str]:
        out_dir = resolve_project_path(str(self.get_parameter("out_dir").value), "data/inventory_images")
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{timestamp_name()}_inventory"
        original_path = out_dir / f"{stem}.jpg"
        annotated_path = out_dir / f"{stem}_annotated.jpg"
        result_path = out_dir / f"{stem}.json"
        cv2.imwrite(str(original_path), frame)
        cv2.imwrite(str(annotated_path), annotated)
        result_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "image_path": str(annotated_path),
            "original_image_path": str(original_path),
            "result_path": str(result_path),
        }

    def _mock_payload(self, reason: str) -> Dict[str, Any]:
        zones = [
            {"zone_id": 1, "zone_name": "vise_1_zone", "registered": 1, "current": 1, "borrowed": 0, "status": "normal"},
            {"zone_id": 2, "zone_name": "vise_2_zone", "registered": 1, "current": 1, "borrowed": 0, "status": "normal"},
            {"zone_id": 3, "zone_name": "insulating_gloves_1_zone", "registered": 1, "current": 1, "borrowed": 0, "status": "normal"},
            {"zone_id": 4, "zone_name": "insulating_gloves_2_zone", "registered": 1, "current": 1, "borrowed": 0, "status": "normal"},
            {"zone_id": 5, "zone_name": "thermometer_1_zone", "registered": 1, "current": 1, "borrowed": 0, "status": "normal"},
            {"zone_id": 6, "zone_name": "thermometer_2_zone", "registered": 1, "current": 1, "borrowed": 0, "status": "normal"},
            {"zone_id": 7, "zone_name": "multimeter_1_zone", "registered": 1, "current": 1, "borrowed": 0, "status": "normal"},
            {"zone_id": 8, "zone_name": "multimeter_2_zone", "registered": 1, "current": 1, "borrowed": 0, "status": "normal"},
        ]
        return {
            "success": True,
            "reason": reason,
            "source": "vision_node_mock",
            "is_normal": True,
            "zones": zones,
            "detections": [],
            "message": "mock inventory normal",
            "image_path": "",
            "timestamp": now_iso(),
        }


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = VisionNode()
        executor = MultiThreadedExecutor(num_threads=2)
        executor.add_node(node)
        executor.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
