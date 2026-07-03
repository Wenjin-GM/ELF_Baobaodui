#!/usr/bin/env python3
"""Live YOLO detection preview for the cabinet interior camera."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QImage, QKeySequence, QPixmap
from PyQt5.QtWidgets import QApplication, QLabel, QMainWindow, QShortcut
from ultralytics import YOLO


DEFAULT_MODEL_PATH = Path("vision/models/best.pt")


def parse_args():
    parser = argparse.ArgumentParser(description="Show live cabinet tool detections.")
    parser.add_argument("--device", default="/dev/video11", help="V4L2 camera device.")
    parser.add_argument(
        "--model",
        default="",
        help="YOLO .pt model path. Defaults to vision/models/best.pt.",
    )
    parser.add_argument("--width", type=int, default=1920, help="Requested capture width.")
    parser.add_argument("--height", type=int, default=1080, help="Requested capture height.")
    parser.add_argument("--imgsz", type=int, default=640, help="YOLO inference image size.")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold.")
    parser.add_argument("--iou", type=float, default=0.45, help="IoU threshold.")
    parser.add_argument("--stride", type=int, default=1, help="Run detection every N frames.")
    parser.add_argument("--window", default="cabinet tool detection", help="Preview window title.")
    parser.add_argument("--save-dir", default="", help="Optional directory for snapshots.")
    parser.add_argument("--display-width", type=int, default=1280, help="Preview window width.")
    parser.add_argument("--display-height", type=int, default=720, help="Preview window height.")
    parser.add_argument("--fullscreen", action="store_true", help="Show preview fullscreen.")
    return parser.parse_args()


def resolve_model_path(model_arg: str) -> Path:
    path = Path(model_arg) if model_arg else DEFAULT_MODEL_PATH
    if path.exists():
        return path
    raise SystemExit(f"model not found: {path}")


def open_camera(device: str, width: int, height: int):
    cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
    if not cap.isOpened():
        cap.release()
        raise RuntimeError(f"cannot open camera: {device}")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    return cap


def draw_status(frame, text: str):
    cv2.rectangle(frame, (8, 8), (8 + 12 * len(text), 42), (0, 0, 0), -1)
    cv2.putText(frame, text, (16, 32), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)


def bgr_to_pixmap(frame):
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    height, width, channels = rgb.shape
    bytes_per_line = channels * width
    image = QImage(rgb.data, width, height, bytes_per_line, QImage.Format_RGB888).copy()
    return QPixmap.fromImage(image)


class LiveDetectionWindow(QMainWindow):
    def __init__(self, args, model, cap, save_dir):
        super().__init__()
        self.args = args
        self.model = model
        self.cap = cap
        self.save_dir = save_dir
        self.last_annotated = None
        self.frame_index = 0
        self.last_time = time.monotonic()
        self.fps = 0.0

        self.setWindowTitle(args.window)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background: black;")
        self.setCentralWidget(self.image_label)
        self.resize(args.display_width, args.display_height)

        QShortcut(QKeySequence("Q"), self, self.close)
        QShortcut(QKeySequence(Qt.Key_Escape), self, self.close)
        QShortcut(QKeySequence("S"), self, self.save_snapshot)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(1)

    def update_frame(self):
        ok, frame = self.cap.read()
        if not ok or frame is None:
            print("[WARN] camera read failed")
            return

        self.frame_index += 1
        if self.frame_index % self.args.stride == 0 or self.last_annotated is None:
            result = self.model.predict(
                source=frame,
                imgsz=self.args.imgsz,
                conf=self.args.conf,
                iou=self.args.iou,
                verbose=False,
            )[0]
            annotated = result.plot()
            detections = len(result.boxes)
            self.last_annotated = annotated
        else:
            detections = -1
            annotated = self.last_annotated.copy()

        now = time.monotonic()
        dt = now - self.last_time
        self.last_time = now
        if dt > 0:
            self.fps = 0.85 * self.fps + 0.15 * (1.0 / dt) if self.fps else 1.0 / dt

        det_text = "cached" if detections < 0 else str(detections)
        draw_status(annotated, f"{self.args.device}  fps={self.fps:.1f}  detections={det_text}")
        self.last_annotated = annotated

        pixmap = bgr_to_pixmap(annotated)
        scaled = pixmap.scaled(self.image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_label.setPixmap(scaled)

    def save_snapshot(self):
        if not self.save_dir or self.last_annotated is None:
            return
        path = self.save_dir / time.strftime("cabinet_detect_%Y%m%d_%H%M%S.jpg")
        cv2.imwrite(str(path), self.last_annotated)
        print(f"[INFO] saved {path}")

    def closeEvent(self, event):
        self.timer.stop()
        self.cap.release()
        super().closeEvent(event)


def main():
    args = parse_args()
    if args.stride < 1:
        raise SystemExit("--stride must be >= 1")

    model_path = resolve_model_path(args.model)

    save_dir = Path(args.save_dir).expanduser() if args.save_dir else None
    if save_dir:
        save_dir.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] loading model: {model_path}")
    model = YOLO(str(model_path))
    print(f"[INFO] names: {model.names}")
    print(f"[INFO] opening camera: {args.device}")
    cap = open_camera(args.device, args.width, args.height)
    actual_width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
    actual_height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
    print(f"[INFO] camera opened: requested={args.width}x{args.height}, actual={actual_width:.0f}x{actual_height:.0f}")

    print("[INFO] PyQt5 preview starting. Press q or ESC to quit; press s to save a snapshot.")
    app = QApplication([])
    window = LiveDetectionWindow(args, model, cap, save_dir)
    if args.fullscreen:
        window.showFullScreen()
    else:
        window.show()
    app.exec_()


if __name__ == "__main__":
    main()
