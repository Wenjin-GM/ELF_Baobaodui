#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PN532 I2C 诊断工具
=================

逐层测试 I2C 通信，帮助定位 PN532 初始化失败的原因。

用法::

    sudo python3 tests/debug_pn532_i2c.py

无需任何额外参数。
"""

import sys
import time

sys.path.insert(0, sys.path[0] + "/..")

import smbus2

BUS  = 7
ADDR = 0x24

# ── PN532 协议常量 ────────────────────────────────────────────────────
HOST_TO_PN532 = 0xD4
PN532_TO_HOST = 0xD5
ACK_PACKET    = [0x00, 0x00, 0xFF, 0x00, 0xFF, 0x00]

def hex_str(data):
    return " ".join(f"{b:02X}" for b in data)


# ======================================================================
# Step 1 — 检查设备是否在 I2C 总线上
# ======================================================================
def step1_device_present():
    print("=" * 55)
    print("[Step 1] 检测 I2C 设备是否在线 (write_quick)")
    print("=" * 55)

    bus = smbus2.SMBus(BUS)
    try:
        bus.write_quick(ADDR)
        print(f"  ✓ 设备 0x{ADDR:02X} ACK 正常 — PN532 在总线上可见")
        return True
    except OSError as e:
        print(f"  ✗ 设备 0x{ADDR:02X} 无 ACK: {e}")
        print(f"  → 请检查: 接线 / i2cdetect -y {BUS} / 3.3V 供电")
        return False
    finally:
        bus.close()


# ======================================================================
# Step 2 — 直接读状态字节
# ======================================================================
def step2_read_status_raw():
    """尝试 3 种不同的读状态方式。"""
    print()
    print("=" * 55)
    print("[Step 2] 读取 PN532 状态字节 (3 种方式)")
    print("=" * 55)
    print("  PN532 空闲时状态 = 0x00, 有数据时 = 0x01")

    # ── 方式 A: 纯读 ──
    print("\n  [A] 纯 I2C 读取 1 字节     ", end="")
    bus = smbus2.SMBus(BUS)
    ok_a = False
    try:
        msg = smbus2.i2c_msg.read(ADDR, 1)
        bus.i2c_rdwr(msg)
        val = list(msg)[0]
        print(f"→ 0x{val:02X}")
        ok_a = True
    except OSError as e:
        print(f"→ 失败: {e}")
    bus.close()

    # ── 方式 B: 写 0x00 + 读 ──
    print("  [B] 写 [0x00] + 读取 1 字节  ", end="")
    bus = smbus2.SMBus(BUS)
    ok_b = False
    try:
        w = smbus2.i2c_msg.write(ADDR, [0x00])
        r = smbus2.i2c_msg.read(ADDR, 1)
        bus.i2c_rdwr(w, r)
        val = list(r)[0]
        print(f"→ 0x{val:02X}")
        ok_b = True
    except OSError as e:
        print(f"→ 失败: {e}")
    bus.close()

    # ── 方式 C: 反复读 3 次看变化 ──
    print("\n  [C] 连续读取 3 次：")
    bus = smbus2.SMBus(BUS)
    for i in range(3):
        try:
            msg = smbus2.i2c_msg.read(ADDR, 1)
            bus.i2c_rdwr(msg)
            val = list(msg)[0]
            print(f"      第{i+1}次 → 0x{val:02X}")
        except OSError as e:
            print(f"      第{i+1}次 → 失败: {e}")
            break
    bus.close()

    return ok_a or ok_b


# ======================================================================
# Step 3 — 发送 GetFirmwareVersion 命令 (纯手工)
# ======================================================================
def step3_send_command_raw():
    print()
    print("=" * 55)
    print("[Step 3] 发送 GetFirmwareVersion (0x02) — 纯手工构造帧")
    print("=" * 55)

    bus = smbus2.SMBus(BUS)

    # ── 构造 PN532 标准帧 ──
    data   = [HOST_TO_PN532, 0x02]          # TFI + CMD
    length = len(data)
    lcs    = (0x100 - length) & 0xFF
    dcs    = (0x100 - sum(data)) & 0xFF
    frame  = [0x00, 0x00, 0xFF, length, lcs] + data + [dcs, 0x00]

    print(f"  PN532 帧: {hex_str(frame)}")

    # ── 方式 A: 直接写帧 ──
    print("\n  [A] 直接写帧                 ", end="")
    ok_a = False
    try:
        msg = smbus2.i2c_msg.write(ADDR, frame)
        bus.i2c_rdwr(msg)
        print("→ 写入成功")
        ok_a = True
    except OSError as e:
        print(f"→ 失败: {e}")

    # ── 方式 B: 写 0x00 + 帧 ──
    print("  [B] 写 [0x00] + 帧           ", end="")
    ok_b = False
    try:
        msg = smbus2.i2c_msg.write(ADDR, [0x00] + frame)
        bus.i2c_rdwr(msg)
        print("→ 写入成功")
        ok_b = True
    except OSError as e:
        print(f"→ 失败: {e}")

    if not (ok_a or ok_b):
        print("  ✗ 两种写入方式均失败")
        bus.close()
        return None

    # ── 轮询等待 ready ──
    print("\n  等待 PN532 ready (最多 2s) …")
    deadline = time.monotonic() + 2.0
    ready = False
    polls = 0
    while time.monotonic() < deadline:
        polls += 1
        try:
            r = smbus2.i2c_msg.read(ADDR, 1)
            bus.i2c_rdwr(r)
            status = list(r)[0]
            if status == 0x01:
                ready = True
                print(f"  ✓ Ready! (第 {polls} 次轮询, {polls*2:.0f}ms)")
                break
        except OSError:
            pass
        time.sleep(0.002)

    if not ready:
        print(f"  ✗ 超时 (轮询 {polls} 次, 约 {polls*2:.0f}ms)")
        print("  → 帧已发出，但 PN532 未响应 ready")
        bus.close()
        return None

    # ── 读响应 ──
    print("\n  读取响应数据 …")
    try:
        r = smbus2.i2c_msg.read(ADDR, 32)
        bus.i2c_rdwr(r)
        raw = list(r)
        print(f"  Raw ({len(raw)} B): {hex_str(raw)}")

        # 找 00 00 FF
        found = False
        for i in range(len(raw) - 2):
            if raw[i] == 0x00 and raw[i+1] == 0x00 and raw[i+2] == 0xFF:
                print(f"\n  ✓ 找到帧起始 00 00 FF 于索引 {i}")
                if len(raw) >= i + 7:
                    flen = raw[i+3]
                    flcs = raw[i+4]
                    tfi  = raw[i+5]
                    cmd  = raw[i+6]
                    print(f"    LEN={flen} LCS=0x{flcs:02X} TFI=0x{tfi:02X} CMD=0x{cmd:02X}")

                    if tfi == PN532_TO_HOST and cmd == 0x03 and len(raw) >= i + 10:
                        ic  = raw[i+7]
                        ver = raw[i+8]
                        rev = raw[i+9]
                        sup = raw[i+10]
                        print(f"\n    ✓✓ 固件: IC=0x{ic:02X} v{ver}.{rev} Support=0x{sup:02X}")
                        found = True
                break

        if not found:
            print("  → 未在响应中找到 00 00 FF 帧头")
            # 检查是否收到 ACK
            if len(raw) >= 6 and raw[:6] == ACK_PACKET:
                print("  → 注意: 响应是 ACK 而非数据帧 (可能还需再读一次)")

    except OSError as e:
        print(f"  ✗ 读取失败: {e}")

    bus.close()
    return found


# ======================================================================
# Step 4 — 尝试多种写帧方式
# ======================================================================
def step4_try_all_write_methods():
    print()
    print("=" * 55)
    print("[Step 4] 尝试不同的 I2C 写/读组合")
    print("=" * 55)

    methods = [
        # (name, write_prefix, use_status_poll)
        ("直接写帧, 纯读状态",         [],       "pure"),
        ("直接写帧, 写0x00+读状态",    [],       "write0"),
        ("写0x00+帧, 纯读状态",        [0x00],   "pure"),
        ("写0x00+帧, 写0x00+读状态",   [0x00],   "write0"),
    ]

    for name, prefix, poll_mode in methods:
        print(f"\n  [{name}]")
        bus = smbus2.SMBus(BUS)

        data   = [HOST_TO_PN532, 0x02]
        length = len(data)
        lcs    = (0x100 - length) & 0xFF
        dcs    = (0x100 - sum(data)) & 0xFF
        frame  = [0x00, 0x00, 0xFF, length, lcs] + data + [dcs, 0x00]
        full   = prefix + frame

        # 写
        try:
            msg = smbus2.i2c_msg.write(ADDR, full)
            bus.i2c_rdwr(msg)
            print("    写 → OK", end="")
        except OSError as e:
            print(f"    写 → 失败: {e}")
            bus.close()
            continue

        # 等 ready
        deadline = time.monotonic() + 2.0
        ready = False
        while time.monotonic() < deadline:
            try:
                if poll_mode == "pure":
                    r = smbus2.i2c_msg.read(ADDR, 1)
                    bus.i2c_rdwr(r)
                else:
                    w = smbus2.i2c_msg.write(ADDR, [0x00])
                    r = smbus2.i2c_msg.read(ADDR, 1)
                    bus.i2c_rdwr(w, r)
                if list(r)[0] == 0x01:
                    ready = True
                    break
            except OSError:
                pass
            time.sleep(0.002)

        if ready:
            print(f"  → Ready ✓")
            # 读响应
            try:
                r = smbus2.i2c_msg.read(ADDR, 32)
                bus.i2c_rdwr(r)
                raw = list(r)
                # 找 00 00 FF
                for i in range(len(raw) - 2):
                    if raw[i]==0x00 and raw[i+1]==0x00 and raw[i+2]==0xFF:
                        print(f"    帧头@{i}, {hex_str(raw[max(0,i-3):i+15])}")
                        break
                else:
                    print(f"    响应: {hex_str(raw[:16])}...")
            except OSError as e:
                print(f"    读响应失败: {e}")
        else:
            print(f"  → 超时 (未ready)")

        bus.close()


# ======================================================================
# Main
# ======================================================================
def main():
    print("PN532 I2C 诊断工具")
    print()
    print(f"  I2C 总线:  /dev/i2c-{BUS}")
    print(f"  I2C 地址:  0x{ADDR:02X}")
    print()

    step1_device_present()
    step2_read_status_raw()
    step3_send_command_raw()
    step4_try_all_write_methods()

    print()
    print("=" * 55)
    print("诊断完成")
    print("=" * 55)
    print()
    print("将以上全部输出发给我，我来分析问题所在。")


if __name__ == "__main__":
    main()
