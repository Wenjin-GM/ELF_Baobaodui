#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
I2C4 一主多从联合测试脚本
验证 PN532 (0x24) 与 SHT30 (0x44) 在 /dev/i2c-4 上共存。

用法:
    python3 scripts/test_i2c4_nfc_sht30_combo.py --timeout 30 --interval 1

• 使用项目现有 PN532/drivers/i2c_pn532.py
• SHT30 使用 smbus2，命令 0x2C 0x06，读 6 字节 CRC8
• PN532 只调用 begin() 和 read_passive_target_id()
• 不写卡、不启动 ROS、不操作门锁
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


def _crc8(data: bytes) -> int:
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x31) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


class SHT30Reader:
    """Minimal SHT30 reader — same protocol as env_node."""

    def __init__(self, bus: int, address: int):
        import smbus2
        self.address = address
        self.bus = smbus2.SMBus(bus)

    def read(self):
        self.bus.write_i2c_block_data(self.address, 0x2C, [0x06])
        time.sleep(0.02)
        data = bytes(self.bus.read_i2c_block_data(self.address, 0x00, 6))
        if _crc8(data[0:2]) != data[2]:
            raise RuntimeError("temperature CRC check failed")
        if _crc8(data[3:5]) != data[5]:
            raise RuntimeError("humidity CRC check failed")
        temp_raw = (data[0] << 8) | data[1]
        hum_raw = (data[3] << 8) | data[4]
        temp = -45.0 + 175.0 * temp_raw / 65535.0
        hum = 100.0 * hum_raw / 65535.0
        return temp, hum

    def close(self):
        self.bus.close()


def main():
    parser = argparse.ArgumentParser(description="I2C4 PN532+SHT30 combo test")
    parser.add_argument("--bus", type=int, default=4, help="I2C bus (default: 4)")
    parser.add_argument("--sht30-addr", type=lambda x: int(x, 0), default=0x44)
    parser.add_argument("--pn532-addr", type=lambda x: int(x, 0), default=0x24)
    parser.add_argument("--timeout", type=int, default=30, help="total test timeout in seconds")
    parser.add_argument("--interval", type=float, default=1.0, help="SHT30 polling interval in seconds")
    args = parser.parse_args()

    # ── ensure project root is on sys.path ──
    project = Path(__file__).resolve().parents[1]
    if str(project) not in sys.path:
        sys.path.insert(0, str(project))

    print(f"=== I2C{args.bus} PN532+SHT30 Combo Test ===")
    print(f"PN532: bus={args.bus} addr=0x{args.pn532_addr:02X}")
    print(f"SHT30: bus={args.bus} addr=0x{args.sht30_addr:02X}")
    print(f"timeout={args.timeout}s  interval={args.interval}s")
    print()

    # ═══ Step 1: Test SHT30 ═══
    print("--- Step 1: SHT30 probe ---")
    sht = None
    try:
        sht = SHT30Reader(args.bus, args.sht30_addr)
        t, h = sht.read()
        print(f"  ✅ SHT30 OK: T={t:.2f}°C  H={h:.2f}%RH")
    except Exception as exc:
        print(f"  ❌ SHT30 read failed: {exc}")
        print("  Abort — fix SHT30 hardware before proceeding.")
        if sht:
            sht.close()
        return 1

    # ═══ Step 2: Test PN532 ═══
    print("--- Step 2: PN532 probe ---")
    nfc = None
    try:
        from PN532.drivers.i2c_pn532 import PN532_I2C
        nfc = PN532_I2C(bus=args.bus, address=args.pn532_addr)
        nfc.begin()
        firmware = nfc.get_firmware_version()
        print(f"  ✅ PN532 OK: firmware={firmware}")
    except Exception as exc:
        print(f"  ❌ PN532 init failed: {exc}")
        print("  Abort — check PN532 wiring/power before proceeding.")
        if sht:
            sht.close()
        return 1

    # ═══ Step 3: Coexistence loop ═══
    print()
    print("--- Step 3: Coexistence loop ---")
    print(f"  Polling SHT30 every {args.interval}s. Place NFC card to test.")
    print(f"  Will run up to {args.timeout}s total.")
    print()

    deadline = time.monotonic() + args.timeout
    nfc_read_count = 0
    sht_ok_count = 0
    sht_fail_count = 0
    last_sht_time = 0.0

    while time.monotonic() < deadline:
        # ── Periodic SHT30 read ──
        now = time.monotonic()
        if now - last_sht_time >= args.interval:
            try:
                t, h = sht.read()
                print(f"  [{now - (deadline - args.timeout):.0f}s] SHT30: T={t:.2f}°C  H={h:.2f}%RH")
                sht_ok_count += 1
            except Exception as exc:
                print(f"  [{now - (deadline - args.timeout):.0f}s] SHT30: ❌ {exc}")
                sht_fail_count += 1
            last_sht_time = now

        # ── NFC card probe ──
        try:
            uid = nfc.read_passive_target_id(timeout=0.3)
            if uid:
                nfc_read_count += 1
                uid_hex = ":".join(f"{b:02X}" for b in uid)
                print(f"  [{now - (deadline - args.timeout):.0f}s] NFC: ✅ UID={uid_hex}")

                # Verify SHT30 still works after NFC read
                time.sleep(0.1)
                try:
                    t2, h2 = sht.read()
                    print(f"  [{now - (deadline - args.timeout):.0f}s] SHT30 after NFC: T={t2:.2f}°C  H={h2:.2f}%RH ✅")
                    sht_ok_count += 1
                except Exception as exc:
                    print(f"  [{now - (deadline - args.timeout):.0f}s] SHT30 after NFC: ❌ {exc}")
                    sht_fail_count += 1

                if nfc_read_count >= 2:
                    print("  NFC card read twice — coexistence verified, stopping early.")
                    break
        except Exception as exc:
            print(f"  [{now - (deadline - args.timeout):.0f}s] NFC probe: ⚠️ {exc}")

        time.sleep(0.1)

    # ═══ Cleanup ═══
    if sht:
        sht.close()
    print()

    # ═══ Summary ═══
    print("=== Coexistence Test Summary ===")
    print(f"  SHT30 reads: {sht_ok_count} OK / {sht_fail_count} FAIL")
    print(f"  NFC reads:   {nfc_read_count}")
    print(f"  Bus:         /dev/i2c-{args.bus}")

    if sht_ok_count > 0 and nfc_read_count > 0 and sht_fail_count == 0:
        print("  ✅ PASS: both devices work on shared I2C bus")
        return 0
    elif sht_ok_count > 0 and nfc_read_count == 0:
        print("  ⚠️  PARTIAL: SHT30 works, no NFC card detected (timeout)")
        return 0
    else:
        print("  ❌ FAIL: check hardware connections")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
