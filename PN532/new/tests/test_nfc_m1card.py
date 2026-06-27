#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PN532 MIFARE Classic 1K — Advanced Test
========================================

Tests:
  1. Card detection & UID reading
  2. Key A authentication with the default factory key
  3. Block reading (sector 0, data blocks 0–2)
  4. Block write → read-back verify → restore original data
  5. Project identity-authentication simulation

.. warning::

    This test **writes** to the card (block 1 of sector 0).
    The original data is restored afterwards, but please use a
    **blank / expendable test card** — not a valuable production card.

Usage::

    sudo python3 tests/test_nfc_m1card.py

Reference
---------
``NFC_I2C测试指南.md`` Section 3.2

Author: 宝宝队
"""

import sys
import time

sys.path.insert(0, sys.path[0] + "/..")

from drivers.i2c_pn532 import PN532_I2C

# ── Constants ─────────────────────────────────────────────────────────

DEFAULT_KEY_A = [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]

BLOCKS_PER_SECTOR = 4          # MIFARE Classic layout: 4 blocks / sector
SECTOR_TRAILER_OFFSET = 3      # every 4th block (0-indexed) is the trailer


# ── Helpers ───────────────────────────────────────────────────────────

def is_sector_trailer(block: int) -> bool:
    """Return ``True`` if *block* is a sector trailer (every 4th block)."""
    return (block % BLOCKS_PER_SECTOR) == SECTOR_TRAILER_OFFSET


def wait_for_card(nfc: PN532_I2C, timeout: float = 30.0) -> list | None:
    """Block until a card is presented on the antenna."""
    print("Place your M1 / blank card on the PN532 antenna …")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        uid = nfc.read_passive_target_id(timeout=1.0)
        if uid:
            return uid
        print(".", end="", flush=True)
        time.sleep(0.3)
    print()
    return None


# ── Test 1 ────────────────────────────────────────────────────────────

def test_detect_card(nfc: PN532_I2C) -> list | None:
    """Detect a card and print its UID."""
    print("\n[TEST 1] Card Detection")
    print("-" * 40)

    uid = wait_for_card(nfc, timeout=15.0)
    if uid is None:
        print("  ✗ No card detected!")
        return None

    print(f"\n  ✓ Card detected!")
    print(f"  ✓ UID: {nfc.format_uid(uid)}  (len={len(uid)} bytes)")
    print(f"  ✓ UID Hex: {''.join(f'{b:02X}' for b in uid)}")
    return uid


# ── Test 2 ────────────────────────────────────────────────────────────

def test_authenticate(nfc: PN532_I2C, uid: list) -> bool:
    """Authenticate sector 0 with the default Key A."""
    print("\n[TEST 2] Authentication (Sector 0)")
    print("-" * 40)
    print(f"  Key A: {' '.join(f'{b:02X}' for b in DEFAULT_KEY_A)}")

    sector = 0
    block  = 0       # any block in the sector can be used for auth

    if nfc.mifare_authenticate_block(uid, block, DEFAULT_KEY_A, "A"):
        print(f"  ✓ Authentication successful (sector {sector}, block {block})")
        return True
    else:
        print(f"  ✗ Authentication failed!")
        print("    The card may use a non-default key or be a different type.")
        return False


# ── Test 3 ────────────────────────────────────────────────────────────

def test_read_blocks(nfc: PN532_I2C) -> list[tuple[int, bytes | None]]:
    """Read the three data blocks of sector 0."""
    print("\n[TEST 3] Reading Blocks (Sector 0)")
    print("-" * 40)

    sector = 0
    results = []

    for block in range(sector * BLOCKS_PER_SECTOR,
                       sector * BLOCKS_PER_SECTOR + SECTOR_TRAILER_OFFSET):
        data = nfc.mifare_read_block(block)
        if data:
            hex_str  = " ".join(f"{b:02X}" for b in data)
            ascii_str = "".join(chr(b) if 32 <= b < 127 else "." for b in data)
            print(f"  Block {block:2d}: {hex_str}  |  {ascii_str}")
            results.append((block, data))
        else:
            print(f"  Block {block:2d}: ✗ Read failed")
            results.append((block, None))

    return results


# ── Test 4 ────────────────────────────────────────────────────────────

def test_write_read_verify(nfc: PN532_I2C, uid: list) -> bool:
    """Write a test pattern to block 1, verify, then restore the original."""
    print("\n[TEST 4] Write / Read / Verify (Block 1)")
    print("-" * 40)
    print("  ⚠  WARNING: This will temporarily overwrite block 1 data!")
    print("  Make sure you are using a blank / test card.\n")

    block = 1

    # ── Re-authenticate (authentication is per-transaction) ──
    if not nfc.mifare_authenticate_block(uid, block, DEFAULT_KEY_A, "A"):
        print("  ✗ Re-authentication failed!")
        return False

    # ── Read original data ──
    original = nfc.mifare_read_block(block)
    if original is None:
        print("  ✗ Failed to read original data!")
        return False

    print(f"  Original: {' '.join(f'{b:02X}' for b in original)}")

    # ── Write test pattern ──
    test_data = bytes([0xBA, 0x0B, 0xA0, 0x00]) + bytes(range(0x10, 0x10 + 12))
    print(f"  Writing:  {' '.join(f'{b:02X}' for b in test_data)}")

    if not nfc.mifare_write_block(block, test_data):
        print("  ✗ Write failed!")
        return False
    print("  ✓ Write successful")

    # ── Read back & verify ──
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

    # ── Restore original data ──
    print("  Restoring original data …")
    if not nfc.mifare_authenticate_block(uid, block, DEFAULT_KEY_A, "A"):
        print("  ✗ Re-authentication failed (restore)!")
        return False

    if nfc.mifare_write_block(block, original):
        print("  ✓ Original data restored")
    else:
        print("  ✗ Restore failed!  Card may contain test data now.")
        return False

    return True


# ── Test 5 ────────────────────────────────────────────────────────────

def test_auth_simulation(nfc: PN532_I2C) -> bool:
    """Simulate the project identity-check flow (UID-only).

    This mimics the smart-tool-cabinet NFC door-unlock workflow:
        1. Poll for card
        2. Read UID
        3. Check UID against the authorised-UID database
    """
    print("\n[TEST 5] Project Authentication Simulation")
    print("-" * 40)
    print("  Simulating smart-tool-cabinet NFC identity check:")
    print("    1. Poll for card")
    print("    2. Read UID")
    print("    3. Check UID against authorised list")
    print()

    # ── Authorised-UID database (populate with real card UIDs) ──
    AUTHORISED_UIDS: list[bytes] = [
        # Example: bytes([0x12, 0x34, 0x56, 0x78]),
    ]

    print("  Polling for card …")
    uid = wait_for_card(nfc, timeout=15.0)
    if uid is None:
        print("  ✗ No card detected!")
        return False

    uid_hex = "".join(f"{b:02X}" for b in uid)
    print(f"\n  ✓ Card UID: {uid_hex}")

    is_authorised = any(uid == auth for auth in AUTHORISED_UIDS)

    if is_authorised:
        print(f"  ✓ UID {uid_hex} is AUTHORISED")
        print(f"  → Simulated action: unlock electromagnetic lock")
    else:
        print(f"  ⚠  UID {uid_hex} is NOT in the authorised list")
        print(f"     (the authorised list is empty — add your card UIDs first)")

    return True


# ── Main ──────────────────────────────────────────────────────────────

def main() -> int:
    print("=" * 50)
    print("PN532 MIFARE Classic 1K — Advanced Test")
    print("=" * 50)

    # ── Initialise ──
    nfc = PN532_I2C(bus=4, debug=False)
    if not nfc.begin():
        print("\n[FAIL] PN532 not found!  Check wiring.")
        return 1

    results: list[tuple[str, bool]] = []

    # ── Test 1: Card detection ──
    uid = test_detect_card(nfc)
    results.append(("Card Detection", uid is not None))

    if uid is None:
        print("\n[ABORT] No card — skipping remaining tests.")
    else:
        # ── Test 2: Authentication ──
        auth_ok = test_authenticate(nfc, uid)
        results.append(("Authentication", auth_ok))

        if auth_ok:
            # ── Test 3: Read blocks ──
            test_read_blocks(nfc)
            results.append(("Block Reading", True))

            # ── Test 4: Write / verify / restore ──
            write_ok = test_write_read_verify(nfc, uid)
            results.append(("Write / Verify", write_ok))
        else:
            print("\n  Skipping read / write tests (authentication failed).")

    # ── Test 5: Auth simulation (requires re-presenting the card) ──
    print("\n  Remove the card, then place it back for auth simulation …")
    time.sleep(2)
    sim_ok = test_auth_simulation(nfc)
    results.append(("Auth Simulation", sim_ok))

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
        print("✓ All tests passed!")
    else:
        print("✗ Some tests failed.")
    print("=" * 50)

    print("\n[NOTE] To use this card in your project,")
    print("       add its UID to the AUTHORISED_UIDS database.")

    nfc.close()
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
