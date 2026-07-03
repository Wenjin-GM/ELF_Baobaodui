#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Standalone PN532 NFC test for the current wiring.

Current wiring:
    PN532 SDA/SCL -> ELF P3/P5 -> /dev/i2c-4
    PN532 I2C address -> 0x24

This script reads UID only. It does not read or write card blocks.
"""

from __future__ import annotations

import argparse
import sys
import time

sys.path.insert(0, sys.path[0] + "/..")

from drivers.i2c_pn532 import PN532_I2C


def uid_to_hex(uid: list[int]) -> str:
    return "".join(f"{byte:02X}" for byte in uid)


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
    parser = argparse.ArgumentParser(description="Test PN532 NFC card UID on I2C4.")
    parser.add_argument("--bus", type=int, default=4, help="I2C bus number, default: 4")
    parser.add_argument("--address", type=lambda value: int(value, 0), default=0x24)
    parser.add_argument("--timeout", type=float, default=30.0, help="Card polling timeout seconds.")
    parser.add_argument("--debug", action="store_true", help="Enable PN532 low-level debug logs.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("=" * 60)
    print("PN532 I2C4 UID Test")
    print("=" * 60)
    print(f"I2C bus: /dev/i2c-{args.bus}")
    print(f"I2C addr: 0x{args.address:02X}")
    print("Mode: read UID only, no card block read/write")
    print("=" * 60)

    nfc = PN532_I2C(bus=args.bus, address=args.address, debug=args.debug)
    try:
        print("[INIT] Initializing PN532...")
        if not nfc.begin():
            print("[FAIL] PN532 initialization failed. Check /dev/i2c-4, 0x24, wiring, power, and I2C mode.")
            return 1

        print(f"[POLL] Place card on PN532. Waiting up to {args.timeout:.1f}s", end="", flush=True)
        uid = wait_for_card(nfc, args.timeout)
        print()
        if not uid:
            print("[FAIL] No card detected.")
            return 2

        uid_hex = uid_to_hex(uid)
        uid_rev = uid_to_hex(list(reversed(uid)))
        print("[CARD] NFC card detected")
        print(f"  UID bytes:        {' '.join(f'{byte:02X}' for byte in uid)}")
        print(f"  UID hex:          {uid_hex}")
        print(f"  UID hex reversed: {uid_rev}")
        print(f"  UID decimal:      {int.from_bytes(bytes(uid), byteorder='big')}")
        print(f"  UID decimal LE:   {int.from_bytes(bytes(uid), byteorder='little')}")
        print(f"  UID length:       {len(uid)} bytes")
        print("[OK] PN532 I2C4 read test passed.")
        return 0
    finally:
        nfc.close()


if __name__ == "__main__":
    raise SystemExit(main())
