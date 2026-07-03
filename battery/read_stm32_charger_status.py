#!/usr/bin/env python3
"""Read STM32 forwarded charger status words on ELF GPIO inputs."""

from __future__ import annotations

import argparse
import json
import select
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import gpiod


SLOT_BITS = (4, 7, 10, 13)
SLOT3_FULL_BIT = 12
VALID_BIT = 15


@dataclass
class Frame:
    word: int
    bit_count: int
    duration_ms: float
    timestamp: str


def now_iso() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")


def decode_word(word: int) -> dict:
    slots = [bool(word & (1 << bit)) for bit in SLOT_BITS]
    valid = bool(word & (1 << VALID_BIT))
    return {
        "module_online": True,
        "status_valid": valid,
        "box_present": any(slots),
        "relay_on": any(slots),
        "slots": slots,
        "battery_levels": [],
        "raw_word": f"0x{word:04X}",
        "raw_word_int": word,
        "slot3_full_candidate": bool(word & (1 << SLOT3_FULL_BIT)),
        "source": "stm32_three_wire_gpio",
        "timestamp": now_iso(),
    }


class Stm32ChargerReader:
    def __init__(self, chip_name: str, data_line: int, clk_line: int, latch_line: int):
        self.chip = gpiod.Chip(chip_name)
        self.data = self.chip.get_line(data_line)
        self.clk = self.chip.get_line(clk_line)
        self.latch = self.chip.get_line(latch_line)

        self.data.request(consumer="battery_data", type=gpiod.LINE_REQ_DIR_IN)
        self.clk.request(consumer="battery_clk", type=gpiod.LINE_REQ_EV_RISING_EDGE)
        self.latch.request(consumer="battery_latch", type=gpiod.LINE_REQ_EV_BOTH_EDGES)

        self.poller = select.poll()
        self.poller.register(self.clk.event_get_fd(), select.POLLIN)
        self.poller.register(self.latch.event_get_fd(), select.POLLIN)

        self.frame_active = False
        self.current_word = 0
        self.bit_index = 0
        self.frame_started_at = 0.0

    def close(self):
        for line in (self.data, self.clk, self.latch):
            try:
                line.release()
            except Exception:
                pass
        try:
            self.chip.close()
        except Exception:
            pass

    def read_frame(self, timeout: float) -> Optional[Frame]:
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None

            events = self.poller.poll(int(remaining * 1000))
            if not events:
                return None

            for fd, _mask in events:
                if fd == self.latch.event_get_fd():
                    event = self.latch.event_read()
                    frame = self._handle_latch_event(event)
                    if frame:
                        return frame
                elif fd == self.clk.event_get_fd():
                    self.clk.event_read()
                    frame = self._handle_clk_rising()
                    if frame:
                        return frame

    def _handle_latch_event(self, event) -> Optional[Frame]:
        if event.type == gpiod.LineEvent.FALLING_EDGE:
            self.frame_active = True
            self.current_word = 0
            self.bit_index = 0
            self.frame_started_at = time.monotonic()
            return None

        if event.type == gpiod.LineEvent.RISING_EDGE:
            if self.frame_active:
                duration_ms = (time.monotonic() - self.frame_started_at) * 1000.0
                frame = Frame(
                    word=self.current_word,
                    bit_count=self.bit_index,
                    duration_ms=duration_ms,
                    timestamp=now_iso(),
                )
                self.frame_active = False
                if frame.bit_count == 16:
                    return frame
            self.frame_active = False
        return None

    def _handle_clk_rising(self) -> Optional[Frame]:
        if not self.frame_active:
            return None
        if self.bit_index >= 16:
            return None
        if self.data.get_value():
            self.current_word |= 1 << self.bit_index
        self.bit_index += 1
        if self.bit_index == 16:
            duration_ms = (time.monotonic() - self.frame_started_at) * 1000.0
            frame = Frame(
                word=self.current_word,
                bit_count=self.bit_index,
                duration_ms=duration_ms,
                timestamp=now_iso(),
            )
            self.frame_active = False
            return frame
        return None


def parse_args():
    parser = argparse.ArgumentParser(description="Read STM32 charger status from ELF GPIO.")
    parser.add_argument("--chip", default="gpiochip3", help="GPIO chip name.")
    parser.add_argument("--data-line", type=int, default=0, help="DATA line offset.")
    parser.add_argument("--clk-line", type=int, default=1, help="CLK rising-edge line offset.")
    parser.add_argument("--latch-line", type=int, default=2, help="LATCH both-edge line offset.")
    parser.add_argument("--frames", type=int, default=5, help="Number of valid frames to print.")
    parser.add_argument("--timeout", type=float, default=5.0, help="Seconds to wait for each frame.")
    parser.add_argument("--max-timeouts", type=int, default=3, help="Stop after this many consecutive timeouts.")
    parser.add_argument("--dump-levels", action="store_true", help="Print DATA/CLK/LATCH levels and exit.")
    parser.add_argument("--json", action="store_true", help="Print decoded payload as JSON lines.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    reader = Stm32ChargerReader(args.chip, args.data_line, args.clk_line, args.latch_line)
    print(
        f"[INFO] reading STM32 charger status: chip={args.chip} "
        f"DATA={args.data_line} CLK={args.clk_line} LATCH={args.latch_line}",
        flush=True,
    )
    try:
        if args.dump_levels:
            print(
                f"DATA={reader.data.get_value()} CLK={reader.clk.get_value()} "
                f"LATCH={reader.latch.get_value()}",
                flush=True,
            )
            return 0

        count = 0
        timeouts = 0
        while count < args.frames:
            frame = reader.read_frame(args.timeout)
            if frame is None:
                timeouts += 1
                print(f"[WARN] timeout waiting for frame ({args.timeout:.1f}s), consecutive={timeouts}", flush=True)
                if timeouts >= args.max_timeouts:
                    print("[ERROR] no complete STM32 status frame received", flush=True)
                    return 2
                continue

            timeouts = 0
            payload = decode_word(frame.word)
            payload["frame_duration_ms"] = round(frame.duration_ms, 3)
            count += 1
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), flush=True)
            else:
                slots_text = ",".join("1" if item else "0" for item in payload["slots"])
                print(
                    f"[FRAME {count}] word={payload['raw_word']} valid={int(payload['status_valid'])} "
                    f"slots=[{slots_text}] box_present={int(payload['box_present'])} "
                    f"slot3_full_candidate={int(payload['slot3_full_candidate'])} "
                    f"duration_ms={payload['frame_duration_ms']}",
                    flush=True,
                )
    finally:
        reader.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
