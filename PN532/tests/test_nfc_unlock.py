#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Standalone NFC-card unlock test for ELF 2 / RK3588.

This script bypasses ROS and verifies the direct hardware chain:
    PN532 on I2C4 -> read card UID -> check authorized card list -> pulse lock relay.

It reads UID only. It does not authenticate card sectors, read card blocks, or
write anything to the card.

Current wiring:
    PN532 SDA/SCL -> P3/P5 -> /dev/i2c-4
    Door lock relay -> GPIO.25 / GPIO3_A3 -> gpiochip3 line 3

Run on the board:
    cd ~/smart_tool_cabinet/PN532
    python3 tests/test_nfc_unlock.py --bus 4 --timeout 30
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import gpiod

sys.path.insert(0, sys.path[0] + "/..")

from drivers.i2c_pn532 import PN532_I2C


DEFAULT_BUS = 4
DEFAULT_ADDRESS = 0x24
DEFAULT_GPIO_CHIP = "gpiochip3"
DEFAULT_LOCK_LINE = 3
DEFAULT_LOCK_PULSE_SECONDS = 0.3
MAX_LOCK_PULSE_SECONDS = 0.5

RELAY_ACTIVE = 0
RELAY_INACTIVE = 1

BUILTIN_CARDS = {
    "19C78529": {"name": "User", "role": "user"},
    "2A86BE5B": {"name": "admin", "role": "admin"},
}


def uid_to_hex(uid: list[int]) -> str:
    return "".join(f"{byte:02X}" for byte in uid)


def find_project_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "authorized_cards.json").exists() or (parent / "PN532").exists():
            return parent
    return here.parents[2]


def load_authorized_cards(path: Path | None) -> dict:
    cards = dict(BUILTIN_CARDS)
    if path is None:
        path = find_project_root() / "authorized_cards.json"
    if not path.exists():
        return cards

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        loaded = data.get("cards", data)
        if isinstance(loaded, dict):
            for uid, info in loaded.items():
                uid_hex = str(uid).strip().upper().replace(" ", "")
                cards[uid_hex] = info if isinstance(info, dict) else {"name": str(info), "role": "user"}
    except Exception as exc:
        print(f"[WARN] Failed to load authorized cards from {path}: {exc}")
    return cards


class ActiveLowRelay:
    def __init__(self, chip_name: str, line_offset: int):
        self.chip_name = chip_name
        self.line_offset = line_offset
        self.chip = gpiod.Chip(chip_name)
        self.line = self.chip.get_line(line_offset)
        try:
            self.line.request(
                consumer="nfc_unlock_test",
                type=gpiod.LINE_REQ_DIR_OUT,
                default_vals=[RELAY_INACTIVE],
            )
        except TypeError:
            self.line.request(consumer="nfc_unlock_test", type=gpiod.LINE_REQ_DIR_OUT)
            self.off()

    def on(self) -> None:
        self.line.set_value(RELAY_ACTIVE)

    def off(self) -> None:
        self.line.set_value(RELAY_INACTIVE)

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


def wait_for_card(nfc: PN532_I2C, timeout: float) -> list[int] | None:
    start = time.time()
    last_dot = 0.0
    while time.time() - start < timeout:
        uid = nfc.read_passive_target_id(timeout=1.0)
        if uid:
            return uid
        now = time.time()
        if now - last_dot >= 0.5:
            print(".", end="", flush=True)
            last_dot = now
        time.sleep(0.1)
    return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read an NFC UID and unlock the door if authorized.")
    parser.add_argument("--bus", type=int, default=DEFAULT_BUS, help="I2C bus number, default: 4")
    parser.add_argument("--address", type=lambda value: int(value, 0), default=DEFAULT_ADDRESS)
    parser.add_argument("--timeout", type=float, default=30.0, help="Card polling timeout seconds.")
    parser.add_argument("--chip", default=DEFAULT_GPIO_CHIP, help="GPIO chip for the lock relay.")
    parser.add_argument("--lock-line", type=int, default=DEFAULT_LOCK_LINE, help="GPIO line for the lock relay.")
    parser.add_argument("--pulse-seconds", type=float, default=DEFAULT_LOCK_PULSE_SECONDS)
    parser.add_argument("--cards", type=Path, help="Optional authorized_cards.json path.")
    parser.add_argument("--no-unlock", action="store_true", help="Only read and authorize UID; do not pulse lock.")
    parser.add_argument("--debug", action="store_true", help="Enable PN532 low-level debug logs.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.pulse_seconds <= 0 or args.pulse_seconds > MAX_LOCK_PULSE_SECONDS:
        print(f"[FAIL] --pulse-seconds must be > 0 and <= {MAX_LOCK_PULSE_SECONDS:.1f}s")
        return 2

    cards = load_authorized_cards(args.cards)
    print("=" * 60)
    print("PN532 NFC Unlock Test")
    print("=" * 60)
    print(f"I2C: /dev/i2c-{args.bus}, addr=0x{args.address:02X}")
    print(f"Lock: {args.chip} line {args.lock_line}, active-low, pulse={args.pulse_seconds:.3f}s")
    print(f"Authorized UIDs: {', '.join(sorted(cards))}")
    print("=" * 60)

    nfc = PN532_I2C(bus=args.bus, address=args.address, debug=args.debug)
    lock = None
    try:
        print("[INIT] Initializing PN532...")
        if not nfc.begin():
            print("[FAIL] PN532 initialization failed. Check I2C bus/address, wiring, power, and I2C mode.")
            return 1

        print(f"[POLL] Place card on PN532. Waiting up to {args.timeout:.1f}s", end="", flush=True)
        uid = wait_for_card(nfc, args.timeout)
        print()
        if not uid:
            print("[FAIL] No card detected.")
            return 3

        uid_hex = uid_to_hex(uid)
        card = cards.get(uid_hex)
        print(f"[CARD] UID={uid_hex} bytes={' '.join(f'{byte:02X}' for byte in uid)}")
        if not card:
            print("[DENY] Card is not authorized. Door lock will not be pulsed.")
            return 4

        name = card.get("name", uid_hex)
        role = card.get("role", "user")
        print(f"[AUTH] Authorized: name={name}, role={role}")

        if args.no_unlock:
            print("[SKIP] --no-unlock set; lock pulse skipped.")
            return 0

        lock = ActiveLowRelay(args.chip, args.lock_line)
        print("[UNLOCK] Pulsing lock relay...")
        lock.pulse(args.pulse_seconds)
        print("[OK] Lock pulse complete.")
        return 0
    finally:
        if lock is not None:
            lock.close()
        nfc.close()


if __name__ == "__main__":
    raise SystemExit(main())
