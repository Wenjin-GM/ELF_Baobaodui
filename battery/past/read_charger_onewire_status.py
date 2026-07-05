#!/usr/bin/env python3
"""Decode the charger box one-wire status signal directly on ELF GPIO."""

from __future__ import annotations

import argparse
import json
import select
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

import gpiod


SLOT_BITS = (4, 7, 10, 13)
SLOT3_FULL_BIT = 12
VALID_BIT = 15


@dataclass
class Edge:
    level: int
    dt_us: int
    timestamp: float


@dataclass
class DecodedFrame:
    raw_word: int
    units: tuple[int, ...]
    levels: str
    bit_string: str
    duration_ms: float


@dataclass
class IntervalFrame:
    intervals_us: list[int]
    units: tuple[int, ...]


def now_iso() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")


def decode_word(word: int, source: str, extra: Optional[dict] = None) -> dict:
    slots = [bool(word & (1 << bit)) for bit in SLOT_BITS]
    payload = {
        "module_online": True,
        "status_valid": bool(word & (1 << VALID_BIT)),
        "box_present": any(slots),
        "relay_on": any(slots),
        "slots": slots,
        "battery_levels": [],
        "raw_word": f"0x{word:04X}",
        "raw_word_int": word,
        "slot3_full_candidate": bool(word & (1 << SLOT3_FULL_BIT)),
        "source": source,
        "timestamp": now_iso(),
    }
    if extra:
        payload.update(extra)
    return payload


def quantize_units(edges: Iterable[Edge], unit_us: float) -> tuple[int, ...]:
    units = []
    for edge in edges:
        unit = round(edge.dt_us / unit_us)
        units.append(max(0, min(255, int(unit))))
    return tuple(units)


def decode_units(units: tuple[int, ...], levels: str) -> Optional[DecodedFrame]:
    if len(units) < 35:
        return None

    # Observed by STM32 firmware: [idle gap], 4T, 3T, 3T, then encoded durations.
    if not (3 <= units[1] <= 5 and 2 <= units[2] <= 4 and 2 <= units[3] <= 4):
        return None

    word = 0
    bits = []
    for bit in range(15):
        a = units[5 + bit * 2]
        b = units[6 + bit * 2]
        if a == 1 and b == 2:
            word |= 1 << bit
            bits.append("1")
        elif a == 2 and b == 1:
            bits.append("0")
        else:
            return None

    word |= 1 << VALID_BIT
    duration_ms = sum(units[1:35]) * 0.0
    return DecodedFrame(raw_word=word, units=units, levels=levels, bit_string="".join(bits), duration_ms=duration_ms)


class OneWireReader:
    def __init__(self, chip_name: str, line_offset: int):
        self.chip = gpiod.Chip(chip_name)
        self.line = self.chip.get_line(line_offset)
        self.line.request(consumer="battery_onewire", type=gpiod.LINE_REQ_EV_BOTH_EDGES)
        self.poller = select.poll()
        self.poller.register(self.line.event_get_fd(), select.POLLIN)
        self.last_ts: Optional[float] = None

    def close(self):
        try:
            self.line.release()
        except Exception:
            pass
        try:
            self.chip.close()
        except Exception:
            pass

    def read_edge(self, timeout: float) -> Optional[Edge]:
        events = self.poller.poll(int(timeout * 1000))
        if not events:
            return None
        event = self.line.event_read()
        now = float(event.sec) + float(event.nsec) / 1_000_000_000.0
        if event.type == gpiod.LineEvent.RISING_EDGE:
            level = 1
        elif event.type == gpiod.LineEvent.FALLING_EDGE:
            level = 0
        else:
            level = int(self.line.get_value())
        if self.last_ts is None:
            dt_us = 0
        else:
            dt_us = int(round((now - self.last_ts) * 1_000_000))
        self.last_ts = now
        return Edge(level=level, dt_us=dt_us, timestamp=now)

    def read_decoded_frame(self, timeout: float, unit_us: float, gap_us: int, debug: bool = False) -> Optional[DecodedFrame]:
        deadline = time.monotonic() + timeout
        current: list[Edge] = []
        patterns = Counter()

        while time.monotonic() < deadline:
            edge = self.read_edge(max(0.001, deadline - time.monotonic()))
            if edge is None:
                continue

            if edge.dt_us > gap_us and current:
                decoded = self._try_decode_current(current, unit_us, patterns, debug)
                current = []
                if decoded:
                    return decoded

            current.append(edge)

        if current:
            decoded = self._try_decode_current(current, unit_us, patterns, debug)
            if decoded:
                return decoded

        if debug and patterns:
            print("[DEBUG] top undecoded normalized patterns:", flush=True)
            for (units, levels), count in patterns.most_common(5):
                print(
                    f"  count={count} edges={len(units)} "
                    f"units_head={units[:80]} levels_head={levels[:120]}",
                    flush=True,
                )
        return None

    def read_interval_frames(self, timeout: float, unit_us: float, gap_us: int, min_interval_us: int) -> list[IntervalFrame]:
        deadline = time.monotonic() + timeout
        frames: list[IntervalFrame] = []
        current: list[int] = []

        while time.monotonic() < deadline:
            edge = self.read_edge(max(0.001, deadline - time.monotonic()))
            if edge is None:
                continue
            if edge.dt_us < min_interval_us:
                continue

            if edge.dt_us > gap_us and current:
                frames.append(IntervalFrame(current, tuple(round(dt / unit_us) for dt in current)))
                current = []

            current.append(edge.dt_us)

        if current:
            frames.append(IntervalFrame(current, tuple(round(dt / unit_us) for dt in current)))
        return frames

    @staticmethod
    def _try_decode_current(current: list[Edge], unit_us: float, patterns: Counter, debug: bool) -> Optional[DecodedFrame]:
        units = quantize_units(current, unit_us)
        levels = "".join(str(edge.level) for edge in current)
        patterns[(units, levels)] += 1
        decoded = decode_units(units, levels)
        if decoded:
            decoded.duration_ms = round(sum(edge.dt_us for edge in current[1:]) / 1000.0, 3)
        elif debug:
            print(
                f"[DEBUG] undecoded frame edges={len(units)} "
                f"units_head={units[:80]} levels_head={levels[:120]}",
                flush=True,
            )
        return decoded


def summarize_interval_frame(index: int, frame: IntervalFrame) -> str:
    units = frame.units
    pairs = list(zip(units, units[1:]))
    short_pairs = [(i, pair) for i, pair in enumerate(pairs) if pair in ((1, 2), (2, 1))]
    return (
        f"[INTERVAL {index}] n={len(units)} units={units[:48]} "
        f"candidate_pairs={short_pairs[:16]}"
    )


def parse_args():
    parser = argparse.ArgumentParser(description="Read charger box one-wire data directly from ELF GPIO.")
    parser.add_argument("--chip", default="gpiochip3", help="GPIO chip name.")
    parser.add_argument("--line", type=int, default=7, help="GPIO line offset for charger DATA.")
    parser.add_argument("--frames", type=int, default=5, help="Number of decoded frames to print.")
    parser.add_argument("--timeout", type=float, default=8.0, help="Seconds to wait for each decoded frame.")
    parser.add_argument("--unit-us", type=float, default=1021.0, help="Protocol time unit in microseconds.")
    parser.add_argument("--gap-us", type=int, default=10000, help="Frame gap threshold in microseconds.")
    parser.add_argument("--json", action="store_true", help="Print decoded payload as JSON lines.")
    parser.add_argument("--debug", action="store_true", help="Print undecoded frame patterns.")
    parser.add_argument("--interval-report", action="store_true", help="Print rising-edge interval frames instead of decoding.")
    parser.add_argument("--min-interval-us", type=int, default=500, help="Ignore intervals shorter than this in report mode.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    reader = OneWireReader(args.chip, args.line)
    print(f"[INFO] reading charger one-wire signal: chip={args.chip} line={args.line}", flush=True)
    try:
        if args.interval_report:
            frames = reader.read_interval_frames(args.timeout, args.unit_us, args.gap_us, args.min_interval_us)
            print(f"[INFO] interval frames={len(frames)} unit_us={args.unit_us} gap_us={args.gap_us}", flush=True)
            for idx, frame in enumerate(frames[: args.frames], 1):
                print(summarize_interval_frame(idx, frame), flush=True)
            return 0

        count = 0
        while count < args.frames:
            frame = reader.read_decoded_frame(args.timeout, args.unit_us, args.gap_us, args.debug)
            if not frame:
                print(f"[WARN] timeout/no decodable frame after {args.timeout:.1f}s", flush=True)
                return 2

            count += 1
            payload = decode_word(
                frame.raw_word,
                "charger_onewire_gpio",
                {
                    "bit_string_lsb_first": frame.bit_string,
                    "frame_duration_ms": frame.duration_ms,
                    "units": list(frame.units[:35]),
                },
            )
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), flush=True)
            else:
                slots_text = ",".join("1" if item else "0" for item in payload["slots"])
                print(
                    f"[FRAME {count}] word={payload['raw_word']} valid={int(payload['status_valid'])} "
                    f"slots=[{slots_text}] box_present={int(payload['box_present'])} "
                    f"slot3_full_candidate={int(payload['slot3_full_candidate'])} "
                    f"bits={frame.bit_string} duration_ms={frame.duration_ms}",
                    flush=True,
                )
    finally:
        reader.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
