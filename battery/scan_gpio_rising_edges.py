#!/usr/bin/env python3
"""Scan GPIO rising-edge activity for locating a clock signal."""

from __future__ import annotations

import argparse
import time


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan GPIO rising edges.")
    parser.add_argument("--chips", nargs="*", default=[f"gpiochip{i}" for i in range(6)])
    parser.add_argument("--seconds", type=float, default=4.0)
    parser.add_argument("--min-count", type=int, default=1)
    args = parser.parse_args()

    import gpiod

    watched = []
    counts = {}
    for chip_name in args.chips:
        try:
            chip = gpiod.Chip(chip_name)
        except Exception as exc:
            print(f"[WARN] open {chip_name} failed: {exc}", flush=True)
            continue

        for offset in range(32):
            try:
                line = chip.get_line(offset)
                line.request(consumer="gpio_rising_scan", type=gpiod.LINE_REQ_EV_RISING_EDGE)
                watched.append((chip_name, chip, offset, line))
                counts[(chip_name, offset)] = 0
            except Exception:
                continue

    deadline = time.monotonic() + args.seconds
    while time.monotonic() < deadline:
        for chip_name, _chip, offset, line in watched:
            try:
                if line.event_wait(sec=0, nsec=0):
                    counts[(chip_name, offset)] += len(line.event_read_multiple())
            except Exception:
                pass
        time.sleep(0.002)

    for _chip_name, chip, _offset, line in watched:
        try:
            line.release()
        except Exception:
            pass
        close = getattr(chip, "close", None)
        if close:
            try:
                close()
            except Exception:
                pass

    active = {
        key: count
        for key, count in sorted(counts.items())
        if count >= args.min_count
    }
    if not active:
        print("no rising-edge activity detected")
        return 1

    for (chip_name, offset), count in active.items():
        print(f"{chip_name} line {offset}: rising_edges={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
