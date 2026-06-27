#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PN532 campus card UID reader.

This script is read-only:
    - It initializes PN532 over I2C4.
    - It polls for an ISO14443A / Mifare-compatible card.
    - It prints UID in spaced hex, compact hex, reversed compact hex, and decimal.

It does not authenticate, read card blocks, or write anything to the card.

Usage:
    cd ~/smart_tool_cabinet/PN532
    sudo python3 tests/test_campus_card_uid.py
"""

import argparse
import sys
import time

sys.path.insert(0, sys.path[0] + "/..")

from drivers.i2c_pn532 import PN532_I2C


def uid_to_hex(uid):
    return "".join(f"{b:02X}" for b in uid)


def uid_to_spaced_hex(uid):
    return " ".join(f"{b:02X}" for b in uid)


def uid_to_decimal(uid):
    return int.from_bytes(bytes(uid), byteorder="big")


def uid_to_reversed_decimal(uid):
    return int.from_bytes(bytes(uid), byteorder="little")


def print_uid(uid):
    uid_bytes = bytes(uid)
    print()
    print("[CARD] Campus card detected")
    print(f"  UID bytes:        {uid_to_spaced_hex(uid)}")
    print(f"  UID hex:          {uid_to_hex(uid)}")
    print(f"  UID hex reversed: {uid_to_hex(list(reversed(uid)))}")
    print(f"  UID decimal:      {uid_to_decimal(uid)}")
    print(f"  UID decimal LE:   {uid_to_reversed_decimal(uid)}")
    print(f"  UID length:       {len(uid_bytes)} bytes")


def wait_for_card(nfc, timeout):
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


def main():
    parser = argparse.ArgumentParser(description="Read campus card UID with PN532 over I2C.")
    parser.add_argument("--bus", type=int, default=4, help="I2C bus number, default: 4")
    parser.add_argument("--timeout", type=float, default=30.0, help="Polling timeout seconds, default: 30")
    parser.add_argument("--debug", action="store_true", help="Enable low-level PN532 debug logs")
    args = parser.parse_args()

    print("=" * 50)
    print("PN532 Campus Card UID Reader")
    print("=" * 50)
    print(f"I2C bus: /dev/i2c-{args.bus}")
    print("Mode: read UID only, no block read/write")
    print("=" * 50)

    nfc = PN532_I2C(bus=args.bus, debug=args.debug)

    try:
        print("\n[INIT] Initializing PN532...")
        if not nfc.begin():
            print("[FAIL] PN532 initialization failed.")
            return 1

        print()
        print("[POLL] Place the campus card on the PN532 antenna.")
        print(f"[POLL] Waiting up to {args.timeout:.1f}s", end="", flush=True)

        uid = wait_for_card(nfc, args.timeout)
        print()

        if not uid:
            print("[FAIL] No card detected.")
            return 2

        print_uid(uid)
        print()
        print("[OK] UID read complete. No data was written to the card.")
        return 0
    finally:
        nfc.close()


if __name__ == "__main__":
    sys.exit(main())
