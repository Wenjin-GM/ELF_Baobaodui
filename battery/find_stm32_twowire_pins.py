#!/usr/bin/env python3
"""Try GPIO DATA/CLK candidates for the STM32 two-wire battery protocol."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROS_PKG = ROOT / "ros2_ws" / "src" / "smart_cabinet_nodes"
if str(ROS_PKG) not in sys.path:
    sys.path.insert(0, str(ROS_PKG))

from smart_cabinet_nodes.battery_reader import TwoWirePresenceReader


def parse_pin(text: str) -> tuple[str, int]:
    if ":" in text:
        chip, line = text.split(":", 1)
    else:
        chip, line = "gpiochip3", text
    return chip, int(line)


def mask_from_slots(slots: list[int]) -> int:
    return sum((1 << i) for i, slot in enumerate(slots[:4]) if slot)


def main() -> int:
    parser = argparse.ArgumentParser(description="Find STM32 two-wire GPIO pins")
    parser.add_argument(
        "--data",
        nargs="+",
        default=["gpiochip3:7"],
        help="DATA candidates as chip:line",
    )
    parser.add_argument(
        "--clk",
        nargs="+",
        default=[
            "gpiochip4:18",
            "gpiochip4:20",
            "gpiochip4:21",
            "gpiochip3:1",
            "gpiochip3:6",
            "gpiochip3:8",
            "gpiochip2:24",
            "gpiochip2:25",
            "gpiochip2:26",
            "gpiochip2:27",
            "gpiochip2:28",
            "gpiochip2:29",
            "gpiochip2:30",
            "gpiochip2:31",
        ],
        help="CLK candidates as chip:line",
    )
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--expect-mask", default=None)
    args = parser.parse_args()

    expected = int(args.expect_mask, 0) if args.expect_mask is not None else None
    found = False
    for data_text in args.data:
        data_chip, data_line = parse_pin(data_text)
        for clk_text in args.clk:
            clk_chip, clk_line = parse_pin(clk_text)
            if data_chip == clk_chip and data_line == clk_line:
                continue
            label = f"DATA={data_chip}:{data_line} CLK={clk_chip}:{clk_line}"
            try:
                with TwoWirePresenceReader(
                    data_chip=data_chip,
                    data_line=data_line,
                    clk_chip=clk_chip,
                    clk_line=clk_line,
                ) as reader:
                    slots, _intervals, info = reader.read_frame_with_info(timeout=args.timeout)
                mask = mask_from_slots(slots)
                status = "PASS"
                if expected is not None and mask != expected:
                    status = "VALID_BUT_UNEXPECTED"
                print(f"{status} {label} slots={slots} mask=0x{mask:X} info={info}", flush=True)
                found = True
            except Exception as exc:
                print(f"FAIL {label}: {exc}", flush=True)

    return 0 if found else 1


if __name__ == "__main__":
    raise SystemExit(main())
