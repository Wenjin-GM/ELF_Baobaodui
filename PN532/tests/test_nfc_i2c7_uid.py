#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Standalone PN532 NFC UID test for ELF i2c-7.

This script is read-only:
  - probes PN532 on /dev/i2c-7 address 0x24
  - reads PN532 firmware version
  - polls one ISO14443A card UID
  - maps known project cards to user/admin

It does not read/write card blocks and does not control the door lock.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from drivers.i2c_pn532 import PN532_I2C


KNOWN_CARDS = {
    "19C78529": {"name": "User", "role": "user"},
    "2A86BE5B": {"name": "admin", "role": "admin"},
}


def uid_hex(uid: list[int]) -> str:
    return "".join(f"{byte:02X}" for byte in uid)


def wait_for_card(nfc: PN532_I2C, timeout: float) -> list[int] | None:
    deadline = time.monotonic() + timeout
    last_dot = 0.0
    while time.monotonic() < deadline:
        uid = nfc.read_passive_target_id(timeout=1.0)
        if uid:
            return uid
        now = time.monotonic()
        if now - last_dot >= 0.5:
            print(".", end="", flush=True)
            last_dot = now
        time.sleep(0.1)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Read one PN532 NFC UID on ELF i2c-7.")
    parser.add_argument("--bus", type=int, default=7, help="I2C bus number, default: 7")
    parser.add_argument("--address", type=lambda value: int(value, 0), default=0x24)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("PN532 I2C7 UID Test")
    print("=" * 60)
    print(f"I2C bus: /dev/i2c-{args.bus}")
    print(f"I2C addr: 0x{args.address:02X}")
    print("Mode: UID read only; no card block read/write; no lock control")
    print("=" * 60)

    try:
        nfc = PN532_I2C(bus=args.bus, address=args.address, debug=args.debug)
    except Exception as exc:
        print(f"[FAIL] Cannot open /dev/i2c-{args.bus}: {exc}")
        return 1

    try:
        print("[INIT] Initializing PN532...")
        if not nfc.begin():
            print("[FAIL] PN532 initialization failed.")
            print("[HINT] If i2cdetect also shows no 0x24 on this bus, check:")
            print("       1. PN532 mode switch/jumper is I2C, not SPI/UART")
            print("       2. SDA/SCL are on the real i2c-7 pins and not swapped")
            print("       3. VCC and GND are connected; ELF and PN532 share GND")
            print("       4. No other process is holding/resetting the module")
            return 2

        print(f"[POLL] Place card on PN532. Waiting up to {args.timeout:.1f}s", end="", flush=True)
        uid = wait_for_card(nfc, args.timeout)
        print()
        if not uid:
            print("[FAIL] No card detected.")
            return 3

        compact = uid_hex(uid)
        reversed_compact = uid_hex(list(reversed(uid)))
        card = KNOWN_CARDS.get(compact)
        print("[CARD] NFC card detected")
        print(f"  UID bytes:        {' '.join(f'{byte:02X}' for byte in uid)}")
        print(f"  UID hex:          {compact}")
        print(f"  UID hex reversed: {reversed_compact}")
        print(f"  UID decimal:      {int.from_bytes(bytes(uid), byteorder='big')}")
        print(f"  UID decimal LE:   {int.from_bytes(bytes(uid), byteorder='little')}")
        print(f"  UID length:       {len(uid)} bytes")
        if card:
            print(f"  Known card:       {card['name']} / {card['role']}")
        else:
            print("  Known card:       no")
        print("[OK] PN532 I2C7 UID read test passed.")
        return 0
    finally:
        nfc.close()


if __name__ == "__main__":
    raise SystemExit(main())
