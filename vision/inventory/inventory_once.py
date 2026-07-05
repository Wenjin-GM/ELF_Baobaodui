#!/usr/bin/env python3
"""Run one cabinet inventory pass from a camera frame or image file."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Tuple

import cv2
from ultralytics import YOLO

from inventory_core import (
    analyze_inventory,
    build_zones_from_detections,
    detections_from_yolo_result,
    expected_counts_from_text,
    load_zones,
    summarize_counts,
    write_zones,
)


def parse_args():
    parser = argparse.ArgumentParser(description="Run one YOLO-based cabinet inventory pass.")
    parser.add_argument("--device", default="/dev/video11", help="Primary V4L2 camera device.")
    parser.add_argument("--fallback-devices", default="/dev/video12,/dev/video0", help="Comma-separated fallback camera devices.")
    parser.add_argument("--image", default="", help="Use an existing image instead of the camera.")
    parser.add_argument("--model", default="vision/best.pt", help="YOLO .pt model path.")
    parser.add_argument("--zones", default="vision/inventory/zones.json", help="Zone config JSON.")
    parser.add_argument("--out", default="data/inventory_images", help="Output directory.")
    parser.add_argument("--width", type=int, default=1920, help="Requested capture width.")
    parser.add_argument("--height", type=int, default=1080, help="Requested capture height.")
    parser.add_argument("--warmup", type=int, default=5, help="Frames to discard before capture.")
    parser.add_argument("--imgsz", type=int, default=960, help="YOLO inference image size.")
    parser.add_argument("--conf", type=float, default=0.02, help="YOLO candidate confidence threshold.")
    parser.add_argument("--iou", type=float, default=0.45, help="IoU threshold.")
    parser.add_argument(
        "--calibrate-from-current",
        action="store_true",
        help="Build zones.json from the current full-and-correct cabinet image.",
    )
    parser.add_argument(
        "--expected-counts",
        default="",
        help='JSON object, default: {"vise":2,"insulating gloves":2,"thermometer":2,"multimeter":2}',
    )
    parser.add_argument("--zone-expand", type=float, default=0.35, help="Calibration bbox expansion ratio.")
    parser.add_argument("--no-save", action="store_true", help="Do not save images/result JSON.")
    parser.add_argument("--json", action="store_true", help="Print compact JSON only.")
    return parser.parse_args()


def open_camera(device: str, width: int, height: int):
    cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
    if not cap.isOpened():
        cap.release()
        raise RuntimeError(f"cannot open camera: {device}")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    return cap


def candidate_devices(primary: str, fallback_text: str):
    devices = []
    for item in [primary, *fallback_text.split(",")]:
        item = item.strip()
        if item and item not in devices:
            devices.append(item)
    return devices


def capture_frame(args) -> Tuple[Any, Dict[str, Any]]:
    if args.image:
        path = Path(args.image).expanduser()
        frame = cv2.imread(str(path))
        if frame is None:
            raise RuntimeError(f"cannot read image: {path}")
        return frame, {"source": "image", "image": str(path)}

    errors = []
    for device in candidate_devices(args.device, args.fallback_devices):
        cap = None
        try:
            cap = open_camera(device, args.width, args.height)
            ok, frame = cap.read()
            if not ok or frame is None:
                errors.append(f"{device}: first read failed")
                continue
            for _ in range(max(0, args.warmup - 1)):
                next_ok, next_frame = cap.read()
                if next_ok and next_frame is not None:
                    frame = next_frame
            return frame, {
                "source": "camera",
                "device": device,
                "requested_width": args.width,
                "requested_height": args.height,
                "actual_width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                "actual_height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            }
        except Exception as exc:
            errors.append(f"{device}: {exc}")
        finally:
            if cap is not None:
                cap.release()
    raise RuntimeError("camera read failed; tried " + "; ".join(errors))


def save_outputs(out_dir: Path, frame, annotated, payload: Dict[str, Any]) -> Dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    suffix = f"{time.time_ns() % 1_000_000_000:09d}"
    original_path = out_dir / f"{stamp}_{suffix}_inventory.jpg"
    annotated_path = out_dir / f"{stamp}_{suffix}_inventory_annotated.jpg"
    result_path = out_dir / f"{stamp}_{suffix}_inventory.json"
    cv2.imwrite(str(original_path), frame)
    cv2.imwrite(str(annotated_path), annotated)
    result_payload = dict(payload)
    result_payload["image_path"] = str(annotated_path)
    result_payload["original_image_path"] = str(original_path)
    result_payload["result_path"] = str(result_path)
    result_path.write_text(json.dumps(result_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "image_path": str(annotated_path),
        "original_image_path": str(original_path),
        "result_path": str(result_path),
    }


def main():
    args = parse_args()
    model_path = Path(args.model).expanduser()
    zones_path = Path(args.zones).expanduser()
    out_dir = Path(args.out).expanduser()
    expected_counts = expected_counts_from_text(args.expected_counts)

    if not model_path.exists():
        raise SystemExit(f"model not found: {model_path}")

    frame, source_info = capture_frame(args)
    height, width = frame.shape[:2]

    model = YOLO(str(model_path))
    result = model.predict(
        source=frame,
        imgsz=args.imgsz,
        conf=args.conf,
        iou=args.iou,
        verbose=False,
    )[0]
    detections = detections_from_yolo_result(result, model.names)
    annotated = result.plot()

    payload: Dict[str, Any] = {
        "success": True,
        "source": source_info,
        "model": str(model_path),
        "model_names": {str(k): v for k, v in getattr(model, "names", {}).items()},
        "image_size": [width, height],
        "counts": summarize_counts(detections),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }

    if args.calibrate_from_current:
        zones_data = build_zones_from_detections(
            detections,
            image_size=[width, height],
            expected_counts=expected_counts,
            expand_ratio=args.zone_expand,
        )
        write_zones(zones_path, zones_data)
        payload.update(
            {
                "mode": "calibrate",
                "zones_path": str(zones_path),
                "zones": zones_data["zones"],
                "is_normal": True,
                "message": f"calibrated {len(zones_data['zones'])} zones",
                "detections": [det.to_dict() for det in detections],
            }
        )
    else:
        if not zones_path.exists():
            raise SystemExit(
                f"zones config not found: {zones_path}\n"
                "Run once with --calibrate-from-current while the cabinet is full and correctly arranged."
            )
        zones_data = load_zones(zones_path)
        analysis = analyze_inventory(detections, zones_data)
        payload.update(
            {
                "mode": "inventory",
                "zones_path": str(zones_path),
                "is_normal": analysis["is_normal"],
                "zones": analysis["zones"],
                "detections": analysis["detections"],
                "unassigned": analysis["unassigned"],
                "message": analysis["message"],
            }
        )

    if not args.no_save:
        saved = save_outputs(out_dir, frame, annotated, payload)
        payload.update(saved)
    else:
        payload.setdefault("image_path", "")

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    else:
        print("===INVENTORY_ONCE_JSON===")
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    return 0 if payload.get("success") and payload.get("is_normal", True) else 1


if __name__ == "__main__":
    sys.exit(main())
