#!/usr/bin/env python3
import argparse
import json
import time
from pathlib import Path

import cv2


def parse_args():
    parser = argparse.ArgumentParser(description="Capture five photos from the USB cabinet-outside camera.")
    parser.add_argument("--device", default="/dev/video21", help="USB camera V4L2 node.")
    parser.add_argument("--count", type=int, default=5, help="Number of photos to capture.")
    parser.add_argument("--width", type=int, default=1280, help="Requested frame width.")
    parser.add_argument("--height", type=int, default=720, help="Requested frame height.")
    parser.add_argument("--fps", type=int, default=30, help="Requested camera FPS.")
    parser.add_argument("--out", default=None, help="Output directory.")
    return parser.parse_args()


def main():
    args = parse_args()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out or f"usb_camera_capture_{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(args.device, cv2.CAP_V4L2)
    if not cap.isOpened():
        raise SystemExit(f"Failed to open camera: {args.device}")

    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    cap.set(cv2.CAP_PROP_FPS, args.fps)

    for _ in range(10):
        cap.read()
        time.sleep(0.05)

    saved = []
    failed = 0
    last_shape = None

    for index in range(1, args.count + 1):
        ok, frame = cap.read()
        if not ok or frame is None:
            failed += 1
            time.sleep(0.2)
            continue

        last_shape = list(frame.shape)
        filename = out_dir / f"usb_camera_{index:02d}.jpg"
        if cv2.imwrite(str(filename), frame):
            saved.append(str(filename))
            print(f"saved {filename}")
        else:
            failed += 1
        time.sleep(0.3)

    cap.release()

    summary = {
        "device": args.device,
        "requested_width": args.width,
        "requested_height": args.height,
        "requested_fps": args.fps,
        "saved_frames": len(saved),
        "failed_reads_or_writes": failed,
        "last_frame_shape": last_shape,
        "out_dir": str(out_dir.resolve()),
        "files": saved,
    }
    (out_dir / "capture_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))

    if len(saved) != args.count:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
