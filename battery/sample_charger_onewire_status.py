#!/usr/bin/env python3
"""Sample and decode the charger box one-wire signal by GPIO polling.

This is a diagnostic fallback for ELF direct wiring. On the current board,
kernel edge events have been observed to report mostly rising edges on
GPIO3_A7, which loses the 1T/2T vs 2T/1T PWM information. A short busy-poll can
reconstruct both high and low pulse widths well enough for this millisecond
protocol.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import gpiod


SLOT_BITS = (4, 7, 10, 13)
SLOT3_FULL_BIT = 12
VALID_BIT = 15


@dataclass(frozen=True)
class Segment:
    level: int
    duration_us: int


@dataclass(frozen=True)
class Frame:
    units: tuple[int, ...]
    levels: str
    durations_us: tuple[int, ...]


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


def sample_segments(chip_name: str, line_offset: int, duration: float) -> tuple[list[Segment], int]:
    chip = gpiod.Chip(chip_name)
    line = chip.get_line(line_offset)
    line.request(consumer="battery_onewire_poll", type=gpiod.LINE_REQ_DIR_IN)

    transitions = 0
    segments: list[Segment] = []
    try:
        last_level = int(line.get_value())
        last_ns = time.perf_counter_ns()
        deadline = time.perf_counter() + duration

        while time.perf_counter() < deadline:
            level = int(line.get_value())
            if level == last_level:
                continue
            now_ns = time.perf_counter_ns()
            segments.append(Segment(last_level, int(round((now_ns - last_ns) / 1000.0))))
            transitions += 1
            last_level = level
            last_ns = now_ns

        now_ns = time.perf_counter_ns()
        segments.append(Segment(last_level, int(round((now_ns - last_ns) / 1000.0))))
    finally:
        line.release()
        chip.close()

    return segments, transitions


def split_frames(segments: list[Segment], unit_us: float, gap_us: int, min_unit: int = 1) -> list[Frame]:
    frames: list[Frame] = []
    current: list[Segment] = []

    for segment in segments:
        if segment.duration_us > gap_us and current:
            frames.append(frame_from_segments(current, unit_us, min_unit))
            current = []
        current.append(segment)

    if current:
        frames.append(frame_from_segments(current, unit_us, min_unit))
    return [frame for frame in frames if len(frame.units) >= 8]


def frame_from_segments(segments: list[Segment], unit_us: float, min_unit: int) -> Frame:
    units = []
    levels = []
    durations = []
    for segment in segments:
        unit = int(round(segment.duration_us / unit_us))
        if unit < min_unit:
            continue
        units.append(max(0, min(255, unit)))
        levels.append(str(segment.level))
        durations.append(segment.duration_us)
    return Frame(tuple(units), "".join(levels), tuple(durations))


def decode_old_pwm(units: tuple[int, ...], start: int) -> Optional[tuple[int, str]]:
    if start + 30 > len(units):
        return None
    word = 1 << VALID_BIT
    bits = []
    for bit in range(15):
        a = units[start + bit * 2]
        b = units[start + bit * 2 + 1]
        if a == 1 and b == 2:
            word |= 1 << bit
            bits.append("1")
        elif a == 2 and b == 1:
            bits.append("0")
        else:
            return None
    return word, "".join(bits)


def try_decode_frame(frame: Frame) -> Optional[tuple[int, str, int]]:
    # The older STM32 firmware decoded from index 5. Keep a small search window
    # because direct ELF polling may include or drop one idle/preamble segment.
    for start in range(0, min(12, len(frame.units))):
        decoded = decode_old_pwm(frame.units, start)
        if decoded:
            word, bits = decoded
            return word, bits, start
    return None


def write_segments(path: Path, segments: list[Segment]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        f.write("index,level,duration_us\n")
        for index, segment in enumerate(segments):
            f.write(f"{index},{segment.level},{segment.duration_us}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Poll and decode charger box one-wire GPIO.")
    parser.add_argument("--chip", default="gpiochip3", help="GPIO chip name.")
    parser.add_argument("--line", type=int, default=7, help="GPIO line offset. GPIO3_A7 is line 7.")
    parser.add_argument("--duration", type=float, default=3.0, help="Sampling duration in seconds.")
    parser.add_argument("--unit-us", type=float, default=1021.0, help="Protocol time unit in microseconds.")
    parser.add_argument("--gap-us", type=int, default=10000, help="Frame gap threshold in microseconds.")
    parser.add_argument("--frames", type=int, default=5, help="Number of decoded or diagnostic frames to print.")
    parser.add_argument("--json", action="store_true", help="Print decoded payloads as JSON lines.")
    parser.add_argument("--debug", action="store_true", help="Print undecoded normalized frames.")
    parser.add_argument("--save", type=Path, help="Optional CSV path for raw sampled segments.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(
        f"[INFO] polling charger one-wire: chip={args.chip} line={args.line} "
        f"duration={args.duration}s",
        flush=True,
    )
    segments, transitions = sample_segments(args.chip, args.line, args.duration)
    frames = split_frames(segments, args.unit_us, args.gap_us)
    print(
        f"[INFO] segments={len(segments)} transitions={transitions} frames={len(frames)} "
        f"unit_us={args.unit_us} gap_us={args.gap_us}",
        flush=True,
    )

    if args.save:
        write_segments(args.save, segments)
        print(f"[INFO] saved sampled segments: {args.save}", flush=True)

    decoded_count = 0
    for frame_index, frame in enumerate(frames, 1):
        decoded = try_decode_frame(frame)
        if not decoded:
            if args.debug and frame_index <= args.frames:
                print(
                    f"[DEBUG] frame={frame_index} n={len(frame.units)} "
                    f"units={frame.units[:80]} levels={frame.levels[:120]}",
                    flush=True,
                )
            continue

        word, bits, start = decoded
        decoded_count += 1
        payload = decode_word(
            word,
            "charger_onewire_gpio_poll",
            {
                "bit_string_lsb_first": bits,
                "decode_start": start,
                "frame_index": frame_index,
                "units": list(frame.units[:80]),
            },
        )
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), flush=True)
        else:
            slots_text = ",".join("1" if item else "0" for item in payload["slots"])
            print(
                f"[FRAME {decoded_count}] word={payload['raw_word']} "
                f"valid={int(payload['status_valid'])} slots=[{slots_text}] "
                f"bits={bits} start={start}",
                flush=True,
            )
        if decoded_count >= args.frames:
            break

    if decoded_count == 0:
        print("[WARN] no decodable old-PWM frame found", flush=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
