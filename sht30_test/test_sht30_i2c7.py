#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Standalone SHT30 temperature/humidity test for the current wiring.

Current wiring:
    SHT30 SDA/SCL -> /dev/i2c-7
    SHT30 I2C address -> 0x44

The script sends the standard high-repeatability single-shot command
0x2C 0x06, reads 6 bytes, validates CRC, and prints temperature/humidity.
"""

from __future__ import annotations

import argparse
import time

import smbus2


def crc8(data: list[int]) -> int:
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x31) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


def read_sht30(bus: smbus2.SMBus, address: int) -> tuple[float, float, list[int]]:
    bus.write_i2c_block_data(address, 0x2C, [0x06])
    time.sleep(0.02)
    data = bus.read_i2c_block_data(address, 0x00, 6)

    temp_crc = crc8(data[0:2])
    hum_crc = crc8(data[3:5])
    if temp_crc != data[2]:
        raise RuntimeError(f"temperature CRC failed: got 0x{data[2]:02X}, expected 0x{temp_crc:02X}, data={data}")
    if hum_crc != data[5]:
        raise RuntimeError(f"humidity CRC failed: got 0x{data[5]:02X}, expected 0x{hum_crc:02X}, data={data}")

    temp_raw = (data[0] << 8) | data[1]
    hum_raw = (data[3] << 8) | data[4]
    temperature = -45.0 + 175.0 * temp_raw / 65535.0
    humidity = 100.0 * hum_raw / 65535.0
    return temperature, humidity, data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test SHT30 on I2C7.")
    parser.add_argument("--bus", type=int, default=7, help="I2C bus number, default: 7")
    parser.add_argument("--address", type=lambda value: int(value, 0), default=0x44)
    parser.add_argument("--count", type=int, default=5, help="Number of reads.")
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between reads.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.count <= 0:
        print("[FAIL] --count must be greater than 0")
        return 2

    print("=" * 60)
    print("SHT30 I2C7 Temperature/Humidity Test")
    print("=" * 60)
    print(f"I2C bus: /dev/i2c-{args.bus}")
    print(f"I2C addr: 0x{args.address:02X}")
    print(f"Reads: {args.count}, interval: {args.interval:.2f}s")
    print("=" * 60)

    bus = smbus2.SMBus(args.bus)
    try:
        for index in range(1, args.count + 1):
            try:
                temperature, humidity, raw = read_sht30(bus, args.address)
                raw_hex = " ".join(f"{byte:02X}" for byte in raw)
                print(
                    f"[READ {index}] T={temperature:.2f} C, "
                    f"H={humidity:.2f} %RH, raw=[{raw_hex}]"
                )
            except Exception as exc:
                print(f"[READ {index}] FAIL: {exc}")
                return 1

            if index != args.count:
                time.sleep(args.interval)

        print("[OK] SHT30 I2C7 read test passed.")
        return 0
    finally:
        bus.close()


if __name__ == "__main__":
    raise SystemExit(main())
