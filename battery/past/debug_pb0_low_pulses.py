#!/usr/bin/env python3
"""Print PB0 low pulse widths and following high widths."""

from __future__ import annotations

import argparse
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chip", default="gpiochip3")
    parser.add_argument("--line", type=int, default=7)
    parser.add_argument("--seconds", type=float, default=12.0)
    args = parser.parse_args()

    import gpiod

    chip = gpiod.Chip(args.chip)
    line = chip.get_line(args.line)
    line.request(consumer="pb0_low_debug", type=gpiod.LINE_REQ_EV_BOTH_EDGES)
    try:
        deadline = time.monotonic() + args.seconds
        edges = []
        while time.monotonic() < deadline:
            if not line.event_wait(sec=1):
                continue
            for ev in line.event_read_multiple():
                ts = float(getattr(ev, "sec", 0)) + float(getattr(ev, "nsec", 0)) / 1_000_000_000.0
                level = 0 if ev.type == gpiod.LineEvent.FALLING_EDGE else 1
                edges.append((ts, level))

        idx = 0
        pulse_no = 0
        while idx < len(edges) - 1:
            if edges[idx][1] != 0:
                idx += 1
                continue
            rise = None
            for j in range(idx + 1, len(edges)):
                if edges[j][1] == 1:
                    rise = j
                    break
                if edges[j][1] == 0:
                    idx = j
                    break
            if rise is None:
                idx += 1
                continue
            high_after = None
            for k in range(rise + 1, len(edges)):
                if edges[k][1] == 0:
                    high_after = (edges[k][0] - edges[rise][0]) * 1000.0
                    break
            low_ms = (edges[rise][0] - edges[idx][0]) * 1000.0
            pulse_no += 1
            high_text = "None" if high_after is None else f"{high_after:8.3f}"
            print(f"{pulse_no:04d}: low={low_ms:8.3f} ms high_after={high_text} ms", flush=True)
            idx = rise + 1
        print(f"edges={len(edges)} pulses={pulse_no}", flush=True)
    finally:
        try:
            line.release()
        finally:
            close = getattr(chip, "close", None)
            if close:
                close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
