#!/usr/bin/env python3
"""Test: wait a fixed delay after ACK, then read response once."""
import sys, time
sys.path.insert(0, '.')
from drivers.i2c_pn532 import PN532_I2C
import smbus2

BUS, ADDR = 7, 0x24

nfc = PN532_I2C(bus=BUS, debug=True)
if not nfc.begin():
    print("INIT FAIL")
    sys.exit(1)

bus = nfc._bus

print("\n=== Strategy: send InListPassiveTarget, wait fixed delay, read ===")

# Manual send
data = [0xD4, 0x4A, 0x01, 0x00]
length = len(data)
lcs = (0x100 - length) & 0xFF
dcs = (0x100 - sum(data)) & 0xFF
frame = [0x00, 0x00, 0xFF, length, lcs] + data + [dcs, 0x00]

bus.i2c_rdwr(smbus2.i2c_msg.write(ADDR, [0x00] + frame))

# Wait for ACK ready
t0 = time.monotonic()
while time.monotonic() - t0 < 2:
    r = smbus2.i2c_msg.read(ADDR, 1)
    bus.i2c_rdwr(r)
    if list(r)[0] == 0x01:
        break

# Read ACK
r = smbus2.i2c_msg.read(ADDR, 7)
bus.i2c_rdwr(r)
print(f"ACK: {' '.join(f'{b:02X}' for b in list(r))}")

# CRITICAL: wait fixed delay for PN532 to scan
for delay in [0.5, 1.0, 2.0]:
    print(f"\n--- Waiting {delay}s before reading ---")
    time.sleep(delay)

    r = smbus2.i2c_msg.read(ADDR, 64)
    bus.i2c_rdwr(r)
    raw = list(r)
    print(f"Raw ({len(raw)}B): {' '.join(f'{b:02X}' for b in raw[:40])}")

    # Look for frame
    for i in range(len(raw) - 2):
        if raw[i]==0x00 and raw[i+1]==0x00 and raw[i+2]==0xFF and i+7 <= len(raw):
            flen = raw[i+3]
            flcs = raw[i+4]
            if ((flen + flcs) & 0xFF) == 0x00 and flen > 0:
                tfi = raw[i+5] if i+5 < len(raw) else -1
                cmd = raw[i+6] if i+6 < len(raw) else -1
                print(f"  ✓ Frame @ {i}: LEN={flen} TFI=0x{tfi:02X} CMD=0x{cmd:02X}")
                if tfi == 0xD5:
                    payload = raw[i+5:i+5+flen]
                    print(f"  Payload: {' '.join(f'{b:02X}' for b in payload)}")
                    if cmd == 0x4B and len(payload) >= 3:
                        nb = payload[2]
                        print(f"  NbTg = {nb}")
                        if nb > 0 and len(payload) >= 8:
                            uid_len = payload[7]
                            uid = payload[8:8+uid_len] if len(payload) >= 8+uid_len else []
                            print(f"  UID: {' '.join(f'{b:02X}' for b in uid)}")

nfc.close()
