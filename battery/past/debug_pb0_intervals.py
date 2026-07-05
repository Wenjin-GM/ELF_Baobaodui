#!/usr/bin/env python3
"""Print raw PB0 rising-edge intervals for battery-box protocol debugging."""

from __future__ import annotations

import argparse
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chip", default="gpiochip3")
    parser.add_argument("--line", type=int, default=7)
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--interval", type=float, default=0.0)
    args = parser.parse_args()

    import gpiod

    chip = gpiod.Chip(args.chip)
    line = chip.get_line(args.line)
    line.request(consumer="pb0_interval_debug", type=gpiod.LINE_REQ_DIR_IN)
    try:
        deadline = time.monotonic() + args.seconds
        last_level = int(line.get_value())
        rising = []
        while time.monotonic() < deadline:
            if args.interval > 0:
                time.sleep(args.interval)
            level = int(line.get_value())
            if level != last_level:
                now = time.monotonic()
                if level == 1:
                    rising.append(now)
                    if len(rising) >= 2:
                        interval_ms = (rising[-1] - rising[-2]) * 1000.0
                        print(f"{len(rising)-1:04d}: {interval_ms:8.3f} ms", flush=True)
                last_level = level
        print(f"rising_edges={len(rising)}", flush=True)
    finally:
        line.release()
        close = getattr(chip, "close", None)
        if close:
            close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
