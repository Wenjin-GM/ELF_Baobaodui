#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fan and electromagnetic lock relay test for ELF 2 / RK3588.

Latest wiring from docs/connect_way.md:
    GPIO.28 -> GPIO2_D3--GPIO3_B1 -> gpiochip3 line 9 -> relay 2 -> fan
    GPIO.25 -> GPIO2_C1--GPIO3_A3 -> gpiochip3 line 3 -> relay 3 -> lock

Relays are treated as active low:
    LOW  = relay on
    HIGH = relay off / safe state

Run on the board:
    cd ~/smart_tool_cabinet
    sudo python3 gpio/test_fan_lock.py
"""

from __future__ import annotations

import argparse
import time

import gpiod


DEFAULT_CHIP = "gpiochip3"
DEFAULT_FAN_LINE = 9
DEFAULT_LOCK_LINE = 3

RELAY_ACTIVE = 0
RELAY_INACTIVE = 1

DEFAULT_FAN_SECONDS = 5.0
DEFAULT_LOCK_PULSES = 3
DEFAULT_LOCK_PULSE_SECONDS = 0.3
DEFAULT_LOCK_GAP_SECONDS = 0.7
MAX_LOCK_PULSE_SECONDS = 0.5


class ActiveLowRelay:
    def __init__(self, chip_name: str, line_offset: int, name: str):
        self.chip_name = chip_name
        self.line_offset = line_offset
        self.name = name
        self.chip = gpiod.Chip(chip_name)
        self.line = self.chip.get_line(line_offset)

        try:
            self.line.request(
                consumer=f"elf2_{name}_test",
                type=gpiod.LINE_REQ_DIR_OUT,
                default_vals=[RELAY_INACTIVE],
            )
        except TypeError:
            self.line.request(
                consumer=f"elf2_{name}_test",
                type=gpiod.LINE_REQ_DIR_OUT,
            )
            self.off()

    def on(self) -> None:
        self.line.set_value(RELAY_ACTIVE)
        print(f"[ON ] {self.name}: {self.chip_name} line {self.line_offset} -> LOW")

    def off(self) -> None:
        self.line.set_value(RELAY_INACTIVE)
        print(f"[OFF] {self.name}: {self.chip_name} line {self.line_offset} -> HIGH")

    def pulse(self, seconds: float) -> None:
        self.on()
        time.sleep(seconds)
        self.off()

    def close(self) -> None:
        try:
            self.off()
        finally:
            self.line.release()
            self.chip.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run fan for 5s, then pulse the lock relay three times."
    )
    parser.add_argument("--chip", default=DEFAULT_CHIP, help="GPIO chip name.")
    parser.add_argument("--fan-line", type=int, default=DEFAULT_FAN_LINE)
    parser.add_argument("--lock-line", type=int, default=DEFAULT_LOCK_LINE)
    parser.add_argument("--fan-seconds", type=float, default=DEFAULT_FAN_SECONDS)
    parser.add_argument("--lock-pulses", type=int, default=DEFAULT_LOCK_PULSES)
    parser.add_argument(
        "--lock-pulse-seconds",
        type=float,
        default=DEFAULT_LOCK_PULSE_SECONDS,
        help="Single lock energizing time. Must be > 0 and <= 0.5s.",
    )
    parser.add_argument("--lock-gap-seconds", type=float, default=DEFAULT_LOCK_GAP_SECONDS)
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.fan_seconds <= 0:
        raise SystemExit("--fan-seconds must be greater than 0")
    if args.lock_pulses <= 0:
        raise SystemExit("--lock-pulses must be greater than 0")
    if args.lock_pulse_seconds <= 0:
        raise SystemExit("--lock-pulse-seconds must be greater than 0")
    if args.lock_pulse_seconds > MAX_LOCK_PULSE_SECONDS:
        raise SystemExit(
            f"--lock-pulse-seconds must be <= {MAX_LOCK_PULSE_SECONDS:.1f}s "
            "to protect the electromagnetic lock"
        )
    if args.lock_gap_seconds < 0:
        raise SystemExit("--lock-gap-seconds must not be negative")


def main() -> None:
    args = parse_args()
    validate_args(args)

    fan = None
    lock = None

    try:
        fan = ActiveLowRelay(args.chip, args.fan_line, "fan")
        lock = ActiveLowRelay(args.chip, args.lock_line, "lock")

        print("[START] Fan and lock relay test")
        print(
            f"[INFO] Fan: {args.chip} line {args.fan_line}, "
            f"run {args.fan_seconds:.1f}s"
        )
        print(
            f"[INFO] Lock: {args.chip} line {args.lock_line}, "
            f"{args.lock_pulses} pulses x {args.lock_pulse_seconds:.3f}s"
        )

        print("[TEST] Fan on")
        fan.on()
        time.sleep(args.fan_seconds)
        fan.off()
        print("[DONE] Fan should have rotated for about 5 seconds")

        for index in range(1, args.lock_pulses + 1):
            print(f"[TEST] Lock pulse {index}/{args.lock_pulses}")
            lock.pulse(args.lock_pulse_seconds)
            if index != args.lock_pulses:
                time.sleep(args.lock_gap_seconds)

        print("[DONE] Lock should have opened/released three times")

    finally:
        if lock is not None:
            lock.close()
        if fan is not None:
            fan.close()
        print("[SAFE] All tested relay lines are set to HIGH / inactive")


if __name__ == "__main__":
    main()
