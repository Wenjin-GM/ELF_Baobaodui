#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Read STM32 PB0 single-wire presence protocol via GPIO on ELF2.

STM32 PB0 outputs a cyclic frame:
  start: low ~300ms, high 100ms
  slot1-4: low 100ms(empty) or 300ms(present), high 100ms
  stop: low 100ms, high 700ms

Decode: find start (low >= 200ms), then 4 slot pulses.
         < 200ms → empty, >= 200ms → present.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

# Import shared reader from ROS package source
_ros_src = Path(__file__).resolve().parents[1] / "ros2_ws" / "src" / "smart_cabinet_nodes"
if str(_ros_src) not in sys.path:
    sys.path.insert(0, str(_ros_src))

from smart_cabinet_nodes.battery_reader import (
    Pb0PollingPresenceReader,
    Pb0PresenceReader,
    build_payload,
)


def mask_from_slots(slots: List[int]) -> int:
    return sum((1 << i) for i, present in enumerate(slots) if present)


def read_stable_frames(
    reader: Pb0PresenceReader,
    frames: int = 3,
    timeout: float = 10.0,
    debug: bool = False,
) -> Tuple[Optional[List[int]], List[List[float]], int, int]:
    """Read N consecutive consistent frames from PB0.
    Returns (slots_or_None, all_widths, frame_count_read).
    """
    deadline = time.monotonic() + timeout
    last_slots: Optional[List[int]] = None
    stable_count = 0
    all_widths: List[List[float]] = []
    total_frames = 0

    while time.monotonic() < deadline and stable_count < frames:
        try:
            remaining = max(2.0, deadline - time.monotonic())
            slots, widths = reader.read_frame(timeout=remaining)
            total_frames += 1
            all_widths.append(widths)

            if last_slots == slots:
                stable_count += 1
            else:
                stable_count = 1
                last_slots = slots

            if debug:
                mask = mask_from_slots(slots)
                print(f"  frame {total_frames}: slots={slots} mask=0x{mask:X} stable={stable_count}/{frames}")

            if stable_count >= frames:
                return last_slots, all_widths, total_frames, stable_count

        except TimeoutError:
            if debug:
                print(f"  timeout after {total_frames} frames")
            break

    if debug:
        print(f"  gave up: {total_frames} frames, stable={stable_count}/{frames}")
    return None, all_widths, total_frames, stable_count


def main():
    parser = argparse.ArgumentParser(description="STM32 PB0 single-wire presence reader")
    parser.add_argument("--chip", default="gpiochip3")
    parser.add_argument("--line", type=int, default=7)
    parser.add_argument("--frames", type=int, default=3, help="consecutive consistent frames required")
    parser.add_argument("--timeout", type=float, default=10.0, help="total timeout in seconds")
    parser.add_argument("--json", action="store_true", help="output JSON to stdout")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--poll", action="store_true", help="use polling (fallback if edges missed)")
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=0.0,
        help="polling interval in seconds; 0.0 means busy-poll for microsecond separators",
    )
    parser.add_argument("--expect-mask", default=None, help="optional expected presence mask, e.g. 0x4 for slot3 only")
    args = parser.parse_args()

    if not args.json:
        print(f"PB0 reader: {args.chip} line {args.line}")
        print(f"  require {args.frames} consistent frames, timeout {args.timeout}s")

    try:
        reader_cls = Pb0PollingPresenceReader if args.poll else Pb0PresenceReader
        reader_kwargs = {"interval_sec": args.poll_interval} if args.poll else {}
        with reader_cls(args.chip, args.line, **reader_kwargs) as reader:
            slots, all_widths, total, stable_count = read_stable_frames(
                reader, frames=args.frames, timeout=args.timeout, debug=args.debug
            )
    except Exception as exc:
        if args.json:
            print(json.dumps(build_payload(None, [], 0, 0), ensure_ascii=False))
        else:
            print(f"ERROR: {exc}")
        return 1

    flat_widths = all_widths[-1] if all_widths else []
    payload = build_payload(slots, flat_widths, stable_count if slots else 0, total)
    expected_mask = int(args.expect_mask, 0) if args.expect_mask is not None else None
    matches_expected = expected_mask is None or payload.get("presence_mask_int") == expected_mask
    stable_enough = int(payload.get("stable_frames", 0)) >= int(args.frames)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(f"  module_online: {payload['module_online']}")
        print(f"  status_valid:  {payload['status_valid']}")
        print(f"  slots:         {payload['slots']}")
        print(f"  presence_mask: {payload['presence_mask']}")
        print(f"  stable_frames: {payload['stable_frames']}/{args.frames}")
        print(f"  total_frames:  {payload['total_frames']}")
        if expected_mask is not None:
            print(f"  expect_mask:   0x{expected_mask:X} -> {'PASS' if matches_expected else 'FAIL'}")
        print(f"  stable_check:  {'PASS' if stable_enough else 'FAIL'}")
        if flat_widths:
            print(f"  pulse_widths:  {[f'{w:.0f}ms' for w in flat_widths]}")

    return 0 if payload["status_valid"] and stable_enough and matches_expected else 1


if __name__ == "__main__":
    raise SystemExit(main())
