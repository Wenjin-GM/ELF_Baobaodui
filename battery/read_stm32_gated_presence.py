#!/usr/bin/env python3
"""Read STM32 PB0/PB1 gated four-bit battery presence from ELF GPIO."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import List


ROOT = Path(__file__).resolve().parents[1]
ROS_PKG = ROOT / "ros2_ws" / "src" / "smart_cabinet_nodes"
if str(ROS_PKG) not in sys.path:
    sys.path.insert(0, str(ROS_PKG))

from smart_cabinet_nodes.battery_reader import GatedPresenceReader, build_payload


def mask_from_slots(slots: List[int]) -> int:
    return sum((1 << i) for i, slot in enumerate(slots[:4]) if slot)


def main() -> int:
    parser = argparse.ArgumentParser(description="STM32 PB0/PB1 gated presence reader")
    parser.add_argument("--data-chip", default="gpiochip3")
    parser.add_argument("--data-line", type=int, default=7)
    parser.add_argument("--frame-chip", default="gpiochip3")
    parser.add_argument("--frame-line", type=int, default=1)
    parser.add_argument("--frames", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--expect-mask", default=None, help="optional expected mask, e.g. 0x7")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    expected_mask = int(args.expect_mask, 0) if args.expect_mask is not None else None
    deadline = time.monotonic() + max(1.0, args.timeout)
    last_slots = None
    stable = 0
    total = 0
    last_timings = []
    last_info = {}

    print(
        "PB0/PB1 gated reader: "
        f"DATA={args.data_chip} line {args.data_line}, "
        f"FRAME_ACTIVE={args.frame_chip} line {args.frame_line}",
        flush=True,
    )
    print(f"  require {args.frames} consistent frames, timeout {args.timeout:.1f}s", flush=True)

    with GatedPresenceReader(
        data_chip=args.data_chip,
        data_line=args.data_line,
        frame_chip=args.frame_chip,
        frame_line=args.frame_line,
    ) as reader:
        while time.monotonic() < deadline and stable < args.frames:
            remaining = max(1.0, deadline - time.monotonic())
            try:
                slots, timings, info = reader.read_frame_with_info(timeout=remaining)
            except Exception as exc:
                if args.debug:
                    print(f"  read failed: {exc}", flush=True)
                break

            total += 1
            last_timings = timings
            last_info = info
            if slots == last_slots:
                stable += 1
            else:
                stable = 1
                last_slots = list(slots)
            if args.debug:
                print(
                    f"  frame {total}: slots={slots} mask=0x{mask_from_slots(slots):X} "
                    f"stable={stable}/{args.frames} info={info}",
                    flush=True,
                )

    payload = build_payload(
        last_slots if stable >= args.frames else None,
        last_timings,
        stable,
        total,
        extra={"frame_info": last_info} if last_info else None,
    )
    matches_expected = expected_mask is None or payload.get("presence_mask_int") == expected_mask

    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(f"  module_online: {payload['module_online']}")
        print(f"  status_valid:  {payload['status_valid']}")
        print(f"  slots:         {payload['slots']}")
        print(f"  presence_mask: {payload['presence_mask']}")
        print(f"  stable_frames: {payload['stable_frames']}/{args.frames}")
        print(f"  total_frames:  {payload['total_frames']}")
        if payload.get("frame_info"):
            print(f"  frame_info:    {payload['frame_info']}")
        if payload.get("error"):
            print(f"  error:         {payload['error']}")
        if expected_mask is not None:
            print(f"  expect_mask:   0x{expected_mask:X} -> {'PASS' if matches_expected else 'FAIL'}")

    return 0 if matches_expected and payload.get("status_valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
