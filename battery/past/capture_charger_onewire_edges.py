#!/usr/bin/env python3
"""Capture raw one-wire charger GPIO edges for protocol analysis."""

from __future__ import annotations

import argparse
import csv
import json
import select
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import gpiod


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def parse_args():
    parser = argparse.ArgumentParser(description="Capture raw charger one-wire GPIO edges.")
    parser.add_argument("--chip", default="gpiochip3", help="GPIO chip name.")
    parser.add_argument("--line", type=int, default=7, help="GPIO line offset.")
    parser.add_argument("--duration", type=float, default=5.0, help="Capture duration in seconds.")
    parser.add_argument("--max-events", type=int, default=5000, help="Maximum edges to capture.")
    parser.add_argument("--out", default="data/battery", help="Output directory.")
    parser.add_argument("--prefix", default="charger_onewire_edges", help="Output file prefix.")
    return parser.parse_args()


def edge_name(event_type: int) -> str:
    if event_type == gpiod.LineEvent.RISING_EDGE:
        return "rising"
    if event_type == gpiod.LineEvent.FALLING_EDGE:
        return "falling"
    return f"unknown_{event_type}"


def main() -> int:
    args = parse_args()
    out_dir = Path(args.out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"{args.prefix}_{now_stamp()}.csv"

    chip = gpiod.Chip(args.chip)
    line = chip.get_line(args.line)
    line.request(consumer="battery_onewire_capture", type=gpiod.LINE_REQ_EV_BOTH_EDGES)

    poller = select.poll()
    poller.register(line.event_get_fd(), select.POLLIN)

    rows = []
    last_ts = None
    start_mono = time.monotonic()
    deadline = start_mono + args.duration

    print(
        f"[INFO] capturing chip={args.chip} line={args.line} "
        f"duration={args.duration}s max_events={args.max_events}",
        flush=True,
    )
    try:
        while time.monotonic() < deadline and len(rows) < args.max_events:
            remaining_ms = max(1, int((deadline - time.monotonic()) * 1000))
            events = poller.poll(remaining_ms)
            if not events:
                continue
            event = line.event_read()
            ts = float(event.sec) + float(event.nsec) / 1_000_000_000.0
            dt_us = 0 if last_ts is None else int(round((ts - last_ts) * 1_000_000))
            last_ts = ts
            rows.append(
                {
                    "index": len(rows),
                    "edge": edge_name(event.type),
                    "event_type": int(event.type),
                    "timestamp_sec": f"{ts:.9f}",
                    "dt_us": dt_us,
                }
            )
    finally:
        line.release()
        chip.close()

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["index", "edge", "event_type", "timestamp_sec", "dt_us"])
        writer.writeheader()
        writer.writerows(rows)

    counts = Counter(row["edge"] for row in rows)
    dts = [row["dt_us"] for row in rows[1:]]
    long_gaps = [dt for dt in dts if dt > 10_000]
    summary = {
        "csv_path": str(csv_path),
        "event_count": len(rows),
        "edge_counts": dict(counts),
        "dt_min_us": min(dts) if dts else None,
        "dt_max_us": max(dts) if dts else None,
        "long_gap_count": len(long_gaps),
        "long_gap_examples_us": long_gaps[:10],
    }
    print("===CHARGER_ONEWIRE_CAPTURE_JSON===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
