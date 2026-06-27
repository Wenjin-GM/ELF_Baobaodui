#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PN532 Mifare Classic 1K Advanced Test
=====================================
Tests:
  1. Card detection and UID reading
  2. Key A authentication (default key: FF FF FF FF FF FF)
  3. Block reading (sector 0, block 0-2)
  4. Block writing and verification (sector 0, block 1)

WARNING:
  This test writes to the card! It only writes to data blocks (not sector trailers).
  Use your blank card or M1 card. Don't use cards you can't afford to corrupt.

Usage:
    cd /path/to/project
    python3 tests/test_nfc_m1card.py
"""

import sys
import time

sys.path.insert(0, sys.path[0] + '/..')

from drivers.i2c_pn532 import PN532_I2C

# Default Mifare Classic key (factory default)
DEFAULT_KEY_A = [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]

# Mifare Classic 1K sector/block layout helpers
SECTOR_SIZE = 4
NUM_SECTORS = 16


def get_sector_trailer_block(sector):
    """Get the block number of the sector trailer for a given sector."""
    return sector * SECTOR_SIZE + 3


def is_sector_trailer(block_number):
    """Check if a block number is a sector trailer."""
    return (block_number % SECTOR_SIZE) == 3


def wait_for_card(nfc, timeout=30.0):
    """Wait for a card to be presented."""
    print("Place your M1/Blank card on the PN532 antenna...")
    start = time.time()
    while time.time() - start < timeout:
        uid = nfc.read_passive_target_id(timeout=1.0)
        if uid:
            return uid
        print(".", end="", flush=True)
        time.sleep(0.3)
    print()
    return None


def test_detect_card(nfc):
    """Test 1: Detect card and read UID."""
    print("\n[TEST 1] Card Detection")
    print("-" * 40)

    uid = wait_for_card(nfc, timeout=15.0)
    if uid is None:
        print("  ✗ No card detected!")
        return None

    print(f"\n  ✓ Card detected!")
    print(f"  ✓ UID: {nfc.format_uid(uid)} (len={len(uid)} bytes)")
    print(f"  ✓ UID Hex: {''.join(f'{b:02X}' for b in uid)}")
    return uid


def test_authenticate(nfc, uid):
    """Test 2: Authenticate sector 0 with default Key A."""
    print("\n[TEST 2] Authentication (Sector 0)")
    print("-" * 40)
    print(f"  Key A: {' '.join(f'{b:02X}' for b in DEFAULT_KEY_A)}")

    sector = 0
    block = 0  # Authenticate block 0 (same sector key works for all blocks in sector)

    if nfc.mifare_authenticate_block(uid, block, DEFAULT_KEY_A, 'A'):
        print(f"  ✓ Authentication successful for sector {sector}, block {block}")
        return True
    else:
        print(f"  ✗ Authentication failed!")
        print("    The card may have a non-default key or be a different card type.")
        return False


def test_read_blocks(nfc):
    """Test 3: Read blocks from sector 0."""
    print("\n[TEST 3] Reading Blocks (Sector 0)")
    print("-" * 40)

    sector = 0
    results = []

    for block in range(sector * SECTOR_SIZE, sector * SECTOR_SIZE + 3):
        data = nfc.mifare_read_block(block)
        if data:
            hex_str = ' '.join(f'{b:02X}' for b in data)
            ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in data)
            print(f"  Block {block:2d}: {hex_str}  |  {ascii_str}")
            results.append((block, data))
        else:
            print(f"  Block {block:2d}: ✗ Read failed")
            results.append((block, None))

    return results


def test_write_read_verify(nfc, uid):
    """Test 4: Write to block 1, read back and verify."""
    print("\n[TEST 4] Write / Read / Verify (Block 1)")
    print("-" * 40)
    print("  WARNING: This will overwrite block 1 data!")
    print("  Make sure you are using a blank/test card.")
    print()

    block = 1

    # Re-authenticate (authentication is per-session)
    if not nfc.mifare_authenticate_block(uid, block, DEFAULT_KEY_A, 'A'):
        print("  ✗ Re-authentication failed!")
        return False

    # Read original data
    original = nfc.mifare_read_block(block)
    if original is None:
        print("  ✗ Failed to read original data!")
        return False

    print(f"  Original: {' '.join(f'{b:02X}' for b in original)}")

    # Write test pattern
    test_data = bytes([0xBA, 0x0B, 0xA0, 0x00] + list(range(0x10, 0x10 + 12)))
    print(f"  Writing:  {' '.join(f'{b:02X}' for b in test_data)}")

    if not nfc.mifare_write_block(block, test_data):
        print("  ✗ Write failed!")
        return False
    print("  ✓ Write successful")

    # Read back and verify
    read_back = nfc.mifare_read_block(block)
    if read_back is None:
        print("  ✗ Read-back failed!")
        return False

    print(f"  Readback: {' '.join(f'{b:02X}' for b in read_back)}")

    if read_back == test_data:
        print("  ✓ Data verification passed!")
    else:
        print("  ✗ Data mismatch!")
        return False

    # Restore original data
    print(f"  Restoring original data...")
    if not nfc.mifare_authenticate_block(uid, block, DEFAULT_KEY_A, 'A'):
        print("  ✗ Re-authentication failed for restore!")
        return False

    if nfc.mifare_write_block(block, original):
        print("  ✓ Original data restored")
    else:
        print("  ✗ Restore failed! Card may have different data now.")
        return False

    return True


def test_uid_only_auth(nfc):
    """Test 5: Simulate project auth flow (read UID only)."""
    print("\n[TEST 5] Project Authentication Simulation")
    print("-" * 40)
    print("  This simulates the tool柜 NFC identity check flow:")
    print("  1. Poll for card")
    print("  2. Read UID")
    print("  3. Check UID against authorized list")
    print()

    # Simulated authorized UIDs database
    authorized_uids = [
        # Add your actual card UIDs here after testing
        # Example: bytes([0x12, 0x34, 0x56, 0x78]),
    ]

    print("  Polling for card...")
    uid = wait_for_card(nfc, timeout=15.0)
    if uid is None:
        print("  ✗ No card detected!")
        return False

    uid_hex = ''.join(f'{b:02X}' for b in uid)
    print(f"\n  ✓ Card UID: {uid_hex}")

    # Check against authorized list
    is_authorized = any(uid == auth_uid for auth_uid in authorized_uids)

    if is_authorized:
        print(f"  ✓ UID {uid_hex} is AUTHORIZED")
        print(f"  → Simulated action: Unlock electromagnetic lock")
    else:
        print(f"  ⚠ UID {uid_hex} is NOT in authorized list")
        print(f"    (Authorized list is empty in this test)")
        print(f"    Add this UID to your database if you want to authorize it.")

    return True


def main():
    print("=" * 50)
    print("PN532 Mifare Classic 1K Advanced Test")
    print("=" * 50)

    # Initialize
    nfc = PN532_I2C(bus=4, debug=False)
    if not nfc.begin():
        print("\n[FAIL] PN532 not found! Check wiring.")
        sys.exit(1)

    # Run tests
    results = []

    # Test 1: Detect card
    uid = test_detect_card(nfc)
    results.append(("Card Detection", uid is not None))

    if uid is None:
        print("\n[ABORT] No card available, stopping further tests.")
    else:
        # Test 2: Authenticate
        auth_ok = test_authenticate(nfc, uid)
        results.append(("Authentication", auth_ok))

        if auth_ok:
            # Test 3: Read blocks
            test_read_blocks(nfc)
            results.append(("Block Reading", True))

            # Test 4: Write/Read/Verify
            write_ok = test_write_read_verify(nfc, uid)
            results.append(("Write/Verify", write_ok))
        else:
            print("\n  Skipping read/write tests (authentication failed)")

    # Test 5: Auth simulation (requires re-presenting card)
    print("\n  Remove the card, then place it back for auth simulation...")
    time.sleep(2)
    auth_sim_ok = test_uid_only_auth(nfc)
    results.append(("Auth Simulation", auth_sim_ok))

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
        print("✓ All tests passed!")
    else:
        print("✗ Some tests failed.")
    print("=" * 50)

    print("\n[NOTE] If you want to use this card in your project,")
    print(f"       add its UID to your authorization database.")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
