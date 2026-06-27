#!/usr/bin/env python3
"""Live camera preview for ELF 2 / RK3588.

Run on the board to see the camera feed in real time:
    python3 vision/camera/board_camera_live_view.py --device /dev/video11

Keys:
    q / Esc  exit
    f        toggle fullscreen
    s        save one snapshot
"""

import argparse
import os
import time
from pathlib import Path

import cv2
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QImage, QKeySequence, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import QApplication, QLabel, QMainWindow, QShortcut


DEFAULT_DEVICES = (
    "/dev/video11",
    "/dev/video-camera0",
    "/dev/video12",
    "/dev/video0",
)


def parse_args():
    parser = argparse.ArgumentParser(description="Show a live camera preview window.")
    parser.add_argument("--device", default=None, help="Preferred V4L2 camera node.")
    parser.add_argument("--devices", nargs="*", default=None, help="Fallback V4L2 nodes.")
    parser.add_argument("--width", type=int, default=1920, help="Requested capture width.")
    parser.add_argument("--height", type=int, default=1080, help="Requested capture height.")
    parser.add_argument("--window-width", type=int, default=1280, help="Preview window width.")
    parser.add_argument("--window-height", type=int, default=720, help="Preview window height.")
    parser.add_argument("--fullscreen", action="store_true", help="Start fullscreen.")
    parser.add_argument("--display", default=None, help="Set DISPLAY, for example :0 over SSH.")
    parser.add_argument("--snapshot-dir", default="/home/elf/camera_live_snapshots")
    return parser.parse_args()


def candidate_devices(args):
    devices = []
    if args.device:
        devices.append(args.device)
    devices.extend(args.devices or DEFAULT_DEVICES)

    unique = []
    seen = set()
    for device in devices:
        if device not in seen:
            seen.add(device)
            unique.append(device)
    return unique


def open_first_camera(devices, width, height):
    errors = []
    for device in devices:
        if not os.path.exists(device):
            errors.append(f"{device}: not found")
            continue

        cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
        if not cap.isOpened():
            cap.release()
            errors.append(f"{device}: open failed")
            continue

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

        for _ in range(8):
            ok, frame = cap.read()
            if ok and frame is not None:
                return device, cap, frame
            time.sleep(0.05)

        cap.release()
        errors.append(f"{device}: no readable frame")

    raise RuntimeError("No usable camera found:\n" + "\n".join(errors))


class CameraWindow(QMainWindow):
    def __init__(self, device, cap, first_frame, args):
        super().__init__()
        self.device = device
        self.cap = cap
        self.args = args
        self.last_frame = first_frame
        self.snapshot_dir = Path(args.snapshot_dir)
        self.snapshot_index = 1
        self.frame_count = 0
        self.fps = 0.0
        self.fps_start = time.monotonic()

        self.label = QLabel()
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("background-color: black; color: white;")
        self.setCentralWidget(self.label)

        self.setWindowTitle("ELF2 Camera Live")
        self.resize(args.window_width, args.window_height)

        QShortcut(QKeySequence("Q"), self, activated=self.close)
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self.close)
        QShortcut(QKeySequence("F"), self, activated=self.toggle_fullscreen)
        QShortcut(QKeySequence("S"), self, activated=self.save_snapshot)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(15)

        if args.fullscreen:
            self.showFullScreen()

    def closeEvent(self, event):
        self.timer.stop()
        self.cap.release()
        super().closeEvent(event)

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def save_snapshot(self):
        stamp = time.strftime("%Y%m%d_%H%M%S")
        filename = self.snapshot_dir / f"live_snapshot_{stamp}_{self.snapshot_index:02d}.jpg"
        if cv2.imwrite(str(filename), self.last_frame):
            print(f"saved {filename}")
            self.snapshot_index += 1
        else:
            print(f"failed to save {filename}")

    def update_frame(self):
        ok, frame = self.cap.read()
        if ok and frame is not None:
            self.last_frame = frame
        else:
            frame = self.last_frame.copy()
            cv2.putText(
                frame,
                "camera read failed",
                (18, 110),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (0, 0, 255),
                3,
            )

        self.frame_count += 1
        elapsed = time.monotonic() - self.fps_start
        if elapsed >= 0.8:
            self.fps = self.frame_count / elapsed
            self.frame_count = 0
            self.fps_start = time.monotonic()

        self.show_frame(frame)

    def show_frame(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height, width = rgb.shape[:2]
        bytes_per_line = 3 * width
        image = QImage(
            rgb.data,
            width,
            height,
            bytes_per_line,
            QImage.Format_RGB888,
        ).copy()

        pixmap = QPixmap.fromImage(image)
        pixmap = pixmap.scaled(
            self.label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )

        painter = QPainter(pixmap)
        painter.setPen(QPen(Qt.black, 5))
        painter.drawText(19, 35, self.overlay_text(width, height))
        painter.setPen(QPen(Qt.green, 2))
        painter.drawText(18, 34, self.overlay_text(width, height))
        painter.end()

        self.label.setPixmap(pixmap)

    def overlay_text(self, width, height):
        mode = "fullscreen" if self.isFullScreen() else "window"
        return (
            f"{self.device}  {width}x{height}  {self.fps:4.1f} FPS  {mode}\n"
            "q/Esc: exit   f: fullscreen   s: snapshot"
        )


def main():
    args = parse_args()

    if args.display:
        os.environ["DISPLAY"] = args.display
    elif not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        os.environ["DISPLAY"] = ":0"

    snapshot_dir = Path(args.snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    device, cap, frame = open_first_camera(candidate_devices(args), args.width, args.height)

    print(f"Live preview started: {device}")
    print("Press q or Esc to exit, f to toggle fullscreen, s to save snapshot.")
    app = QApplication([])
    window = CameraWindow(device, cap, frame, args)
    window.show()
    raise SystemExit(app.exec_())


if __name__ == "__main__":
    main()
