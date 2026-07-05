#!/usr/bin/env python3
"""Analyze direct charger one-wire GPIO captures.

The charger box now exposes only one useful signal line. This helper keeps the
analysis evidence-based: it splits captured GPIO edge CSV files into frames,
normalizes intervals to protocol time units, and highlights candidate bit
positions for a known battery-slot state.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


SLOT_BITS = (4, 7, 10, 13)
VALID_BIT = 15


@dataclass(frozen=True)
class Frame:
    intervals_us: tuple[int, ...]
    units: tuple[int, ...]
    edges: tuple[str, ...]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze charger one-wire GPIO edge CSV.")
    parser.add_argument("csv_path", type=Path, help="CSV produced by capture_charger_onewire_edges.py.")
    parser.add_argument("--unit-us", type=float, default=1021.0, help="Protocol time unit in microseconds.")
    parser.add_argument("--gap-us", type=int, default=10000, help="Frame gap threshold in microseconds.")
    parser.add_argument("--min-interval-us", type=int, default=500, help="Ignore shorter intervals as glitches.")
    parser.add_argument("--top", type=int, default=12, help="Number of top patterns to print.")
    parser.add_argument(
        "--expected-slots",
        default="0101",
        help="Expected slot occupancy, slot1..slot4, e.g. 0101 means slots 2 and 4 occupied.",
    )
    return parser.parse_args()


def load_rows(csv_path: Path) -> list[tuple[str, int]]:
    rows: list[tuple[str, int]] = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append((row["edge"], int(row["dt_us"])))
    return rows


def split_frames(rows: list[tuple[str, int]], unit_us: float, gap_us: int, min_interval_us: int) -> list[Frame]:
    frames: list[Frame] = []
    intervals: list[int] = []
    edges: list[str] = []

    for index, (edge, dt_us) in enumerate(rows):
        if index == 0:
            continue
        if dt_us > gap_us and intervals:
            frames.append(
                Frame(
                    tuple(intervals),
                    tuple(round(item / unit_us) for item in intervals),
                    tuple(edges),
                )
            )
            intervals = []
            edges = []
        if dt_us >= min_interval_us:
            intervals.append(dt_us)
            edges.append(edge)

    if intervals:
        frames.append(
            Frame(
                tuple(intervals),
                tuple(round(item / unit_us) for item in intervals),
                tuple(edges),
            )
        )
    return frames


def short_pair_positions(units: tuple[int, ...]) -> list[tuple[int, tuple[int, int], str]]:
    out = []
    for idx in range(len(units) - 1):
        pair = (units[idx], units[idx + 1])
        if pair == (1, 2):
            out.append((idx, pair, "one_if_old_pwm"))
        elif pair == (2, 1):
            out.append((idx, pair, "zero_if_old_pwm"))
    return out


def expected_word(expected_slots: str) -> int:
    if len(expected_slots) != 4 or any(ch not in "01" for ch in expected_slots):
        raise ValueError("--expected-slots must be four characters of 0/1")
    word = 1 << VALID_BIT
    for occupied, bit in zip(expected_slots, SLOT_BITS):
        if occupied == "1":
            word |= 1 << bit
    return word


def old_pwm_decode_at(units: tuple[int, ...], start: int, bit_count: int = 15) -> tuple[int, str] | None:
    if start + bit_count * 2 > len(units):
        return None
    word = 1 << VALID_BIT
    bits = []
    for bit in range(bit_count):
        pair = (units[start + bit * 2], units[start + bit * 2 + 1])
        if pair == (1, 2):
            word |= 1 << bit
            bits.append("1")
        elif pair == (2, 1):
            bits.append("0")
        else:
            return None
    return word, "".join(bits)


def print_pattern(index: int, count: int, frame: Frame, expected: int) -> None:
    print(f"{index}. count={count} intervals={len(frame.units)}")
    print(f"   units={frame.units}")
    print(f"   edges={''.join(edge[0].upper() for edge in frame.edges)}")
    print(f"   short_pairs={short_pair_positions(frame.units)}")

    matches = []
    for start in range(min(12, len(frame.units))):
        decoded = old_pwm_decode_at(frame.units, start)
        if decoded:
            word, bits = decoded
            matches.append((start, word, bits, word == expected))
    for start, word, bits, is_expected in matches:
        mark = " MATCH_EXPECTED" if is_expected else ""
        print(f"   old_pwm start={start}: word=0x{word:04X} bits_lsb_first={bits}{mark}")


def main() -> int:
    args = parse_args()
    rows = load_rows(args.csv_path)
    frames = split_frames(rows, args.unit_us, args.gap_us, args.min_interval_us)
    edge_counts = Counter(edge for edge, _ in rows)
    patterns = Counter(frames)
    expected = expected_word(args.expected_slots)

    print(f"capture={args.csv_path}")
    print(f"rows={len(rows)} edge_counts={dict(edge_counts)} split_frames={len(frames)}")
    print(f"unit_us={args.unit_us} gap_us={args.gap_us} min_interval_us={args.min_interval_us}")
    print(f"expected_slots={args.expected_slots} expected_word=0x{expected:04X}")
    print()
    print("Top normalized patterns:")
    for idx, (frame, count) in enumerate(patterns.most_common(args.top), 1):
        print_pattern(idx, count, frame, expected)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
