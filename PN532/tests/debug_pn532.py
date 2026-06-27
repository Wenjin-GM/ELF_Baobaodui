#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PN532 I2C 调试脚本 - 用于排查通信问题
"""

import sys
import time

sys.path.insert(0, sys.path[0] + '/..')
from drivers.i2c_pn532 import PN532_I2C


def test_i2c_raw_communication():
    """测试最底层的 I2C 读写。"""
    print("=" * 50)
    print("Debug: PN532 I2C Raw Communication Test")
    print("=" * 50)

    nfc = PN532_I2C(bus=4, debug=True)

    # Step 1: 测试读取状态字节
    print("\n[Step 1] Reading status byte 3 times...")
    for i in range(3):
        status = nfc._read_status()
        print(f"  Read {i+1}: 0x{status:02X}")
        time.sleep(0.1)

    # Step 2: 发送 GetFirmwareVersion 命令
    print("\n[Step 2] Sending GetFirmwareVersion (0x02)...")
    command = 0x02
    data = [0xD4, command]
    frame = nfc._build_frame(data)
    print(f"  Frame to send: {' '.join(f'{b:02X}' for b in frame)}")

    try:
        nfc._write_data(frame)
        print("  Write OK")
    except Exception as e:
        print(f"  Write FAILED: {e}")
        return

    # Step 3: 等待 Ready
    print("\n[Step 3] Waiting for PN532 ready...")
    ready = nfc._wait_ready(timeout=2.0)
    print(f"  Ready: {ready}")

    if not ready:
        print("  [WARN] PN532 not ready, trying to read status again...")
        for i in range(5):
            status = nfc._read_status()
            print(f"    Status {i+1}: 0x{status:02X}")
            time.sleep(0.1)
        return

    # Step 4: 读取响应
    print("\n[Step 4] Reading response...")
    try:
        # 先多读几个字节，看看原始数据
        raw = nfc._read_data(20)
        print(f"  Raw data (20 bytes): {' '.join(f'{b:02X}' for b in raw)}")
    except Exception as e:
        print(f"  Read FAILED: {e}")
        return

    # Step 5: 尝试解析
    print("\n[Step 5] Parsing response...")
    # 找到 0xFF 的位置（跳过 preamble 0x00）
    ff_idx = -1
    for i, b in enumerate(raw):
        if b == 0xFF:
            ff_idx = i
            break

    if ff_idx == -1:
        print("  No 0xFF found in response!")
        return

    print(f"  0xFF found at index {ff_idx}")
    if ff_idx + 5 < len(raw):
        length = raw[ff_idx + 1]
        lcs = raw[ff_idx + 2]
        tfi = raw[ff_idx + 3]
        resp_cmd = raw[ff_idx + 4]
        print(f"  LEN: {length}, LCS: 0x{lcs:02X}, TFI: 0x{tfi:02X}, RESP_CMD: 0x{resp_cmd:02X}")

        if tfi == 0xD5 and resp_cmd == 0x03:
            payload = raw[ff_idx + 5:ff_idx + 5 + 4]
            print(f"  Firmware: IC=0x{payload[0]:02X}, Ver={payload[1]}.{payload[2]}, Support=0x{payload[3]:02X}")


def test_wakeup():
    """测试发送唤醒序列（某些 PN532 模块需要）。"""
    print("\n" + "=" * 50)
    print("Debug: Testing Wake-Up sequence")
    print("=" * 50)

    import smbus2
    bus = smbus2.SMBus(4)
    addr = 0x24

    # Wake-up: 发送多个 0x00
    print("\n[Sending wake-up 0x00 x 10...]")
    try:
        msg = smbus2.i2c_msg.write(addr, [0x00] * 10)
        bus.i2c_rdwr(msg)
        print("  Wake-up write OK")
    except Exception as e:
        print(f"  Wake-up write FAILED: {e}")

    time.sleep(0.1)

    # 再读状态
    print("\n[Reading status after wake-up...]")
    for i in range(3):
        try:
            msg = smbus2.i2c_msg.read(addr, 1)
            bus.i2c_rdwr(msg)
            status = list(msg)[0]
            print(f"  Status {i+1}: 0x{status:02X}")
        except Exception as e:
            print(f"  Read FAILED: {e}")
        time.sleep(0.1)


def test_without_preamble():
    """测试不带额外 0x00 前导的帧。"""
    print("\n" + "=" * 50)
    print("Debug: Testing frame without extra 0x00 preamble")
    print("=" * 50)

    import smbus2
    bus = smbus2.SMBus(4)
    addr = 0x24

    # 构建标准帧（不带 _write_data 里额外加的 0x00）
    nfc = PN532_I2C(bus=4, debug=False)
    data = [0xD4, 0x02]
    frame = nfc._build_frame(data)

    print(f"\nFrame: {' '.join(f'{b:02X}' for b in frame)}")

    # 直接发送，不加额外的 0x00
    print("[Sending without extra 0x00 prefix...]")
    try:
        msg = smbus2.i2c_msg.write(addr, frame)
        bus.i2c_rdwr(msg)
        print("  Write OK")
    except Exception as e:
        print(f"  Write FAILED: {e}")

    time.sleep(0.05)

    # 等待 ready
    print("[Waiting for ready...]")
    start = time.time()
    ready = False
    while time.time() - start < 2.0:
        try:
            msg = smbus2.i2c_msg.read(addr, 1)
            bus.i2c_rdwr(msg)
            status = list(msg)[0]
            if status == 0x01:
                ready = True
                print(f"  Ready! (status=0x01)")
                break
        except:
            pass
        time.sleep(0.01)

    if ready:
        print("[Reading response...]")
        try:
            msg = smbus2.i2c_msg.read(addr, 20)
            bus.i2c_rdwr(msg)
            raw = list(msg)
            print(f"  Raw: {' '.join(f'{b:02X}' for b in raw)}")
        except Exception as e:
            print(f"  Read FAILED: {e}")


if __name__ == "__main__":
    print("PN532 I2C Debug Tool")
    print("This script will try multiple communication methods.\n")

    test_wakeup()
    test_without_preamble()
    test_i2c_raw_communication()

    print("\n" + "=" * 50)
    print("Debug tests completed.")
    print("=" * 50)
