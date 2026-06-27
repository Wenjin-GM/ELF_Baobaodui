#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PN532 NFC Basic Test Script
===========================
Tests:
  1. PN532 communication (read firmware version)
  2. SAM configuration
  3. Card detection (poll for UID)

Usage:
    cd /path/to/project
    python3 tests/test_nfc_basic.py

Requirements:
    - smbus2 (pip3 install smbus2)
    - PN532 connected to RK3588 I2C4
"""

import sys
import time

# Add parent directory to path for imports
sys.path.insert(0, sys.path[0] + '/..')

from drivers.i2c_pn532 import PN532_I2C


def test_firmware_version(nfc):
    """Test 1: Read PN532 firmware version."""
    print("\n[TEST 1] Reading firmware version...")
    fw = nfc.get_firmware_version()
    if fw:
        print(f"  ✓ IC Version: 0x{fw['ic']:02X}")
        print(f"  ✓ Firmware:   v{fw['ver']}.{fw['rev']}")
        print(f"  ✓ Support:    0x{fw['support']:02X}")
        return True
    else:
        print("  ✗ Failed to read firmware version!")
        return False


def test_sam_config(nfc):
    """Test 2: Configure SAM."""
    print("\n[TEST 2] Configuring SAM...")
    if nfc.sam_configuration():
        print("  ✓ SAM configured successfully")
        return True
    else:
        print("  ✗ SAM configuration failed!")
        return False


def test_card_detection(nfc):
    """Test 3: Detect NFC card and read UID."""
    print("\n[TEST 3] Polling for NFC card...")
    print("  → Place your card/keyfob on the PN532 antenna")
    print("  → Waiting up to 10 seconds...")

    start = time.time()
    detected = False

    while time.time() - start < 10.0:
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


def main():
    print("=" * 50)
    print("PN532 I2C Basic Test")
    print("=" * 50)
    print(f"I2C Bus: 4  |  Device: /dev/i2c-4")
    print("Expected I2C address: 0x24 (PN532)")
    print("=" * 50)

    # Initialize PN532
    print("\n[INIT] Initializing PN532...")
    nfc = PN532_I2C(bus=4, debug=False)

    if not nfc.begin():
        print("\n[FAIL] PN532 initialization failed!")
        print("Common causes:")
        print("  1. Wrong wiring (SDA/SCL swapped?)")
        print("  2. Wrong I2C bus (not /dev/i2c-4?)")
        print("  3. No 3.3V power to PN532")
        print("  4. I2C address conflict (try: sudo i2cdetect -y 4)")
        sys.exit(1)

    results = []

    # Run tests
    results.append(("Firmware Version", test_firmware_version(nfc)))
    results.append(("SAM Configuration", test_sam_config(nfc)))
    results.append(("Card Detection", test_card_detection(nfc)))

    # Summary
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

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
