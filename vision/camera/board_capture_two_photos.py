#!/usr/bin/env python3
"""Capture two still photos from an ELF 2 / RK3588 camera when requested."""

import argparse
import json
import os
import time
from pathlib import Path

import cv2


DEFAULT_DEVICES = (
    "/dev/video11",
    "/dev/video-camera0",
    "/dev/video12",
    "/dev/video0",
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Probe or capture still images from the ELF 2 camera."
    )
    parser.add_argument("--probe", action="store_true", help="Check camera readiness only.")
    parser.add_argument("--count", type=int, default=2, help="Number of photos to save.")
    parser.add_argument("--device", default=None, help="Preferred V4L2 camera node.")
    parser.add_argument("--devices", nargs="*", default=None, help="Fallback V4L2 nodes.")
    parser.add_argument("--out", default=None, help="Output directory on the board.")
    parser.add_argument("--width", type=int, default=1920, help="Requested frame width.")
    parser.add_argument("--height", type=int, default=1080, help="Requested frame height.")
    parser.add_argument("--warmup", type=int, default=10, help="Frames to discard first.")
    parser.add_argument("--interval", type=float, default=0.6, help="Seconds between photos.")
    return parser.parse_args()


def candidate_devices(args):
    devices = []
    if args.device:
        devices.append(args.device)
    devices.extend(args.devices or DEFAULT_DEVICES)

    seen = set()
    unique = []
    for device in devices:
        if device not in seen:
            seen.add(device)
            unique.append(device)
    return unique


def open_camera(device, width, height):
    cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
    if not cap.isOpened():
        cap.release()
        return None

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    return cap


def warm_camera(cap, frames):
    last_shape = None
    readable = False
    for _ in range(max(frames, 0)):
        ok, frame = cap.read()
        if ok and frame is not None:
            readable = True
            last_shape = list(frame.shape)
        time.sleep(0.05)
    return readable, last_shape


def probe_devices(devices, width, height, warmup):
    results = []
    for device in devices:
        result = {"device": device, "exists": os.path.exists(device)}
        if result["exists"]:
            cap = open_camera(device, width, height)
            result["opened"] = cap is not None
            if cap is not None:
                readable, shape = warm_camera(cap, min(warmup, 3))
                result["readable"] = readable
                result["shape"] = shape
                result["reported_width"] = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                result["reported_height"] = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
                cap.release()
        results.append(result)
    return results


def capture_from_device(device, args, out_dir):
    cap = open_camera(device, args.width, args.height)
    if cap is None:
        return {"device": device, "opened": False, "saved": []}

    readable, last_shape = warm_camera(cap, args.warmup)
    saved = []
    failed = 0

    for index in range(1, args.count + 1):
        ok, frame = cap.read()
        if not ok or frame is None:
            failed += 1
            time.sleep(args.interval)
            continue

        last_shape = list(frame.shape)
        filename = out_dir / f"camera_{Path(device).name}_{index:02d}.jpg"
        if cv2.imwrite(str(filename), frame):
            saved.append(str(filename))
        else:
            failed += 1
        time.sleep(args.interval)

    result = {
        "device": device,
        "opened": True,
        "readable": readable or bool(saved),
        "shape": last_shape,
        "saved": saved,
        "failed_reads_or_writes": failed,
        "reported_width": cap.get(cv2.CAP_PROP_FRAME_WIDTH),
        "reported_height": cap.get(cv2.CAP_PROP_FRAME_HEIGHT),
    }
    cap.release()
    return result


def main():
    args = parse_args()
    if args.count <= 0:
        raise SystemExit("--count must be greater than 0")
    if args.interval < 0:
        raise SystemExit("--interval must not be negative")

    devices = candidate_devices(args)

    if args.probe:
        summary = {
            "mode": "probe",
            "devices": probe_devices(devices, args.width, args.height, args.warmup),
        }
        print(json.dumps(summary, ensure_ascii=False))
        if not any(item.get("readable") for item in summary["devices"]):
            raise SystemExit(2)
        return

    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out or f"/home/elf/camera_two_photos_{stamp}")
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for device in devices:
        if not os.path.exists(device):
            results.append({"device": device, "exists": False, "saved": []})
            continue
        result = capture_from_device(device, args, out_dir)
        results.append(result)
        if len(result.get("saved", [])) >= args.count:
            break

    summary = {
        "mode": "capture",
        "out_dir": str(out_dir),
        "requested_count": args.count,
        "results": results,
    }
    summary_path = out_dir / "capture_summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))

    if not any(item.get("saved") for item in results):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
