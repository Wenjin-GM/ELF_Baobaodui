#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PN532 NFC Basic Test
====================

Tests:
  1. PN532 communication  — read firmware version
  2. SAM configuration
  3. Card detection        — poll for ISO14443A / MIFARE card UID

Usage::

    sudo python3 tests/test_nfc_basic.py

Expected output matches ``NFC_I2C测试指南.md`` Section 3.1.

Hardware requirements
---------------------
- PN532 I2C mode → RK3588 40Pin (see NFC_I2C测试指南.md for wiring)
- Python ≥ 3.7 + smbus2

Author: 宝宝队
"""

import sys
import time

# Allow running from the ``new/`` directory directly
sys.path.insert(0, sys.path[0] + "/..")

from drivers.i2c_pn532 import PN532_I2C


# ── Test 1 ────────────────────────────────────────────────────────────

def test_firmware_version(nfc: PN532_I2C) -> bool:
    """Read PN532 firmware version and print it."""
    print("\n[TEST 1] Reading firmware version...")

    fw = nfc.get_firmware_version()
    if fw is None:
        print("  ✗ Failed to read firmware version!")
        return False

    print(f"  ✓ IC Version: 0x{fw['ic']:02X}")
    print(f"  ✓ Firmware:   v{fw['ver']}.{fw['rev']}")
    print(f"  ✓ Support:    0x{fw['support']:02X}")
    return True


# ── Test 2 ────────────────────────────────────────────────────────────

def test_sam_config(nfc: PN532_I2C) -> bool:
    """Configure PN532 SAM (normal mode)."""
    print("\n[TEST 2] Configuring SAM...")

    if nfc.sam_configuration():
        print("  ✓ SAM configured successfully")
        return True
    else:
        print("  ✗ SAM configuration failed!")
        return False


# ── Test 3 ────────────────────────────────────────────────────────────

def test_card_detection(nfc: PN532_I2C) -> bool:
    """Poll for an NFC card and print its UID."""
    print("\n[TEST 3] Polling for NFC card...")
    print("  → Place your card/keyfob on the PN532 antenna")
    print("  → Waiting up to 10 seconds...")

    deadline = time.monotonic() + 10.0
    detected = False

    while time.monotonic() < deadline:
        uid = nfc.read_passive_target_id(timeout=1.0)
        if uid:
            print(f"  ✓ Card detected!")
            print(f"  ✓ UID: {nfc.format_uid(uid)} (len={len(uid)})")
            detected = True
            break
        time.sleep(0.3)

    if not detected:
        print("  ✗ No card detected within 10 seconds")
        print("    Tips:")
        print("    - Make sure the card is placed directly on the antenna area")
        print("    - Check that VCC=3.3V and GND is connected")
        print("    - Try a different card/keyfob")

    return detected


# ── Main ──────────────────────────────────────────────────────────────

def main() -> int:
    print("=" * 50)
    print("PN532 I2C Basic Test")
    print("=" * 50)
    print("I2C Bus: 7  |  Device: /dev/i2c-7")
    print("Expected I2C address: 0x24 (PN532)")
    print("=" * 50)

    # ── Initialise ──
    print("\n[INIT] Initializing PN532...")
    nfc = PN532_I2C(bus=7, debug=False)

    if not nfc.begin():
        print("\n[FAIL] PN532 initialization failed!")
        print("Common causes:")
        print("  1. Wrong wiring (SDA/SCL swapped?)")
        print("  2. Wrong I2C bus (not /dev/i2c-7?)")
        print("  3. No 3.3V power to PN532")
        print("  4. I2C address conflict (try: sudo i2cdetect -y 4)")
        return 1

    results: list[tuple[str, bool]] = []

    # ── Run tests ──
    results.append(("Firmware Version", test_firmware_version(nfc)))
    results.append(("SAM Configuration", test_sam_config(nfc)))
    results.append(("Card Detection",    test_card_detection(nfc)))

    # ── Summary ──
    print("\n" + "=" * 50)
    print("Test Summary")
    print("=" * 50)

    all_pass = True
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
        if not passed:
            all_pass = False

    print("=" * 50)
    if all_pass:
        print("✓ All tests passed! PN532 is working correctly.")
    else:
        print("✗ Some tests failed. Check the output above.")
    print("=" * 50)

    nfc.close()
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
