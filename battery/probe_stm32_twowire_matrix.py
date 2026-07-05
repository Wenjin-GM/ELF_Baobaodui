#!/usr/bin/env python3
"""Probe one CLK candidate against many DATA candidates for STM32 two-wire frames."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROS_PKG = ROOT / "ros2_ws" / "src" / "smart_cabinet_nodes"
if str(ROS_PKG) not in sys.path:
    sys.path.insert(0, str(ROS_PKG))

from smart_cabinet_nodes.battery_reader import (
    TWOWIRE_BITS,
    _decode_twowire_frame,
    _edge_timestamp,
)


def parse_pin(text: str) -> tuple[str, int]:
    chip, line = text.split(":", 1)
    return chip, int(line)


def mask_from_bits(mask: int) -> list[int]:
    return [1 if (mask & (1 << i)) else 0 for i in range(4)]


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe two-wire DATA candidates using one CLK.")
    parser.add_argument("--clk", required=True, help="CLK as chip:line")
    parser.add_argument(
        "--data",
        nargs="+",
        required=True,
        help="DATA candidates as chip:line",
    )
    parser.add_argument("--seconds", type=float, default=5.0)
    parser.add_argument("--gap-ms", type=float, default=150.0)
    args = parser.parse_args()

    import gpiod

    clk_chip_name, clk_line_offset = parse_pin(args.clk)
    clk_chip = gpiod.Chip(clk_chip_name)
    clk_line = clk_chip.get_line(clk_line_offset)
    clk_line.request(consumer="tw_probe_clk", type=gpiod.LINE_REQ_EV_RISING_EDGE)

    data_lines = []
    for text in args.data:
        chip_name, offset = parse_pin(text)
        try:
            chip = gpiod.Chip(chip_name)
            line = chip.get_line(offset)
            line.request(consumer="tw_probe_data", type=gpiod.LINE_REQ_DIR_IN)
            data_lines.append((text, chip, line))
        except Exception as exc:
            print(f"SKIP DATA={text}: {exc}", flush=True)

    bits = {text: [] for text, _chip, _line in data_lines}
    last_ts = None
    edges = 0
    invalid = {text: 0 for text, _chip, _line in data_lines}
    deadline = time.monotonic() + args.seconds
    found = False

    try:
        while time.monotonic() < deadline:
            remaining = max(0.001, deadline - time.monotonic())
            sec = int(min(1.0, remaining))
            nsec = int((min(1.0, remaining) - sec) * 1_000_000_000)
            if not clk_line.event_wait(sec=sec, nsec=nsec):
                continue

            for ev in clk_line.event_read_multiple():
                now = _edge_timestamp(ev)
                edges += 1
                if last_ts is not None and (now - last_ts) * 1000.0 > args.gap_ms:
                    for text in bits:
                        bits[text] = []
                last_ts = now

                for text, _chip, line in data_lines:
                    bits[text].append(int(line.get_value()))
                    if len(bits[text]) < TWOWIRE_BITS:
                        continue
                    frame = 0
                    for index, bit in enumerate(bits[text][:TWOWIRE_BITS]):
                        frame |= (int(bit) & 0x01) << index
                    try:
                        mask, info = _decode_twowire_frame(frame)
                    except Exception:
                        invalid[text] += 1
                        bits[text] = []
                        continue
                    print(
                        f"PASS CLK={args.clk} DATA={text} "
                        f"slots={mask_from_bits(mask)} mask=0x{mask:X} info={info}",
                        flush=True,
                    )
                    found = True
                    bits[text] = []
    finally:
        try:
            clk_line.release()
        except Exception:
            pass
        close = getattr(clk_chip, "close", None)
        if close:
            close()
        for _text, chip, line in data_lines:
            try:
                line.release()
            except Exception:
                pass
            close = getattr(chip, "close", None)
            if close:
                close()

    print(f"CLK={args.clk} edges={edges} invalid={invalid}", flush=True)
    return 0 if found else 1


if __name__ == "__main__":
    raise SystemExit(main())
