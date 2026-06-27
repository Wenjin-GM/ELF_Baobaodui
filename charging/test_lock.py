#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Active-low relay / electromagnetic lock pulse test for ELF 2 RK3588.

Latest wiring from docs/connect_way.md:
    GPIO.25 -> GPIO2_C1--GPIO3_A3 -> gpiochip3 line 3
    relay 3 -> electromagnetic lock, active low

Run on the board:
    cd ~/smart_tool_cabinet
    sudo python3 charging/test_lock.py
"""

import argparse
import time

import gpiod


DEFAULT_CHIP = "gpiochip3"
DEFAULT_LINE = 3
DEFAULT_PULSE_SECONDS = 0.5
SETTLE_SECONDS = 0.05
RELAY_INACTIVE = 1
RELAY_ACTIVE = 0


def request_output_line(chip_name: str, line_offset: int, initial_value: int):
    chip = gpiod.Chip(chip_name)
    line = chip.get_line(line_offset)

    try:
        line.request(
            consumer="lock_relay_active_low",
            type=gpiod.LINE_REQ_DIR_OUT,
            default_vals=[initial_value],
        )
    except TypeError:
        line.request(consumer="lock_relay_active_low", type=gpiod.LINE_REQ_DIR_OUT)
        line.set_value(initial_value)

    return chip, line


def pulse_lock(chip_name: str, line_offset: int, pulse_seconds: float):
    chip = None
    line = None

    try:
        chip, line = request_output_line(chip_name, line_offset, RELAY_INACTIVE)
        print(f"[SAFE] {chip_name} line {line_offset} -> HIGH, relay inactive")
        time.sleep(SETTLE_SECONDS)

        print(f"[OPEN] {chip_name} line {line_offset} -> LOW for {pulse_seconds:.3f}s")
        line.set_value(RELAY_ACTIVE)
        time.sleep(pulse_seconds)
    finally:
        if line is not None:
            line.set_value(RELAY_INACTIVE)
            print(f"[SAFE] {chip_name} line {line_offset} -> HIGH, relay inactive")
            line.release()
        if chip is not None:
            chip.close()


def main():
    parser = argparse.ArgumentParser(description="Pulse active-low lock relay on ELF 2 GPIO.25.")
    parser.add_argument("--chip", default=DEFAULT_CHIP, help="GPIO chip name, default: gpiochip3")
    parser.add_argument("--line", type=int, default=DEFAULT_LINE, help="GPIO line offset, default: 3")
    parser.add_argument(
        "--seconds",
        type=float,
        default=DEFAULT_PULSE_SECONDS,
        help="Low-level pulse time in seconds, default: 0.5",
    )
    args = parser.parse_args()

    if args.seconds <= 0 or args.seconds > 2.0:
        raise ValueError("--seconds must be > 0 and <= 2.0 for lock safety")

    pulse_lock(args.chip, args.line, args.seconds)


if __name__ == "__main__":
    main()
