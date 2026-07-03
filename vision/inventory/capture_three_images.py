#!/usr/bin/env python3
"""Capture three cabinet-camera images for dataset collection."""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import cv2


def parse_args():
    parser = argparse.ArgumentParser(description="Capture three images from the cabinet camera.")
    parser.add_argument("--device", default="/dev/video11", help="V4L2 camera device.")
    parser.add_argument("--out", default="data/inventory_dataset/raw", help="Output directory.")
    parser.add_argument("--count", type=int, default=3, help="Number of images to capture.")
    parser.add_argument("--interval", type=float, default=0.6, help="Seconds between saved images.")
    parser.add_argument("--warmup", type=int, default=5, help="Frames to discard before capture.")
    parser.add_argument("--width", type=int, default=1920, help="Requested capture width.")
    parser.add_argument("--height", type=int, default=1080, help="Requested capture height.")
    parser.add_argument("--prefix", default="cabinet", help="Filename prefix.")
    return parser.parse_args()


def open_camera(device: str, width: int, height: int):
    cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
    if not cap.isOpened():
        cap.release()
        raise RuntimeError(f"cannot open camera: {device}")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    return cap


def main():
    args = parse_args()
    if args.count < 1:
        raise SystemExit("--count must be >= 1")
    if args.interval < 0:
        raise SystemExit("--interval must be >= 0")

    out_dir = Path(args.out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    cap = open_camera(args.device, args.width, args.height)
    actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[INFO] camera opened: {args.device}, requested={args.width}x{args.height}, actual={actual_width}x{actual_height}")

    saved = []
    try:
        for _ in range(max(0, args.warmup)):
            cap.read()

        batch_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        for index in range(1, args.count + 1):
            ok, frame = cap.read()
            if not ok or frame is None:
                print(f"[WARN] capture {index}/{args.count} failed")
                continue

            filename = f"{args.prefix}_{batch_stamp}_{index:02d}.jpg"
            path = out_dir / filename
            if cv2.imwrite(str(path), frame):
                saved.append(str(path))
                print(f"[INFO] saved {path}")
            else:
                print(f"[WARN] failed to write {path}")

            if index < args.count and args.interval > 0:
                time.sleep(args.interval)
    finally:
        cap.release()

    print("===CAPTURE_THREE_IMAGES_JSON===")
    print(json.dumps({
        "device": args.device,
        "out_dir": str(out_dir),
        "requested_count": args.count,
        "saved_count": len(saved),
        "saved": saved,
        "actual_width": actual_width,
        "actual_height": actual_height,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
