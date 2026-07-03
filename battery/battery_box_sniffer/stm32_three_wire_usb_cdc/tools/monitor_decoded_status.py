from __future__ import annotations

import argparse
import re
import struct
import time
from collections import Counter

import serial
from serial.tools import list_ports


FRAME0 = 0xA5
FRAME1 = 0x5A
TYPE_EDGE = 0xE1
TYPE_STATUS = 0x5A
TYPE_DECODED = 0xD5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Monitor STM32 decoded charger status over USB CDC.")
    parser.add_argument("--port", default=None, help="Serial port, e.g. COM3. Auto-detect if omitted.")
    parser.add_argument("--seconds", type=float, default=15.0)
    parser.add_argument("--expected", default="0xA080", help="Expected status word for success judgment.")
    parser.add_argument(
        "--expected-mask",
        default=None,
        help="Expected stable presence mask. bit0..bit3 are slot1..slot4, e.g. 0xE for slot2/3/4.",
    )
    return parser.parse_args()


def find_port() -> str:
    ports = list(list_ports.comports())
    for port in ports:
        text = " ".join(str(x) for x in (port.device, port.description, port.hwid))
        if "0483:5740" in text.upper() or "THREE WIRE" in text.upper() or "STM" in text.upper():
            return port.device
    if len(ports) == 1:
        return ports[0].device
    raise SystemExit("No STM32 USB CDC serial port found. Pass --port COMx after checking Device Manager.")


def iter_frames(buf: bytearray):
    while len(buf) >= 5:
        if buf[0] != FRAME0 or buf[1] != FRAME1:
            del buf[0]
            continue
        typ = buf[2]
        ln = buf[3]
        frame_len = 5 + ln
        if len(buf) < frame_len:
            return
        payload = bytes(buf[4 : 4 + ln])
        crc = typ ^ ln
        for value in payload:
            crc ^= value
        got = buf[frame_len - 1]
        del buf[:frame_len]
        if (crc & 0xFF) == got:
            yield typ, payload


def decode_word(word: int) -> str:
    valid = bool(word & 0x8000)
    slots = [
        bool(word & 0x0010),
        bool(word & 0x0080),
        bool(word & 0x0400),
        bool(word & 0x2000),
    ]
    slot_text = " ".join(f"slot{i + 1}={'1' if present else '0'}" for i, present in enumerate(slots))
    return f"word=0x{word:04X} valid={int(valid)} {slot_text} slot3_full_candidate={int(bool(word & 0x1000))}"


def decode_presence_mask(mask: int) -> str:
    return " ".join(f"p{i + 1}={(mask >> i) & 1}" for i in range(4))


def main() -> int:
    args = parse_args()
    expected = int(args.expected, 0)
    expected_mask = int(args.expected_mask, 0) if args.expected_mask is not None else None
    port = args.port or find_port()

    start = time.monotonic()
    buf = bytearray()
    words: Counter[int] = Counter()
    raw_masks: Counter[int] = Counter()
    stable_masks: Counter[int] = Counter()
    last_print = 0.0
    decoded_frames = 0
    edge_count_s = 0

    expected_mask_text = f" expected_mask=0x{expected_mask:X}" if expected_mask is not None else ""
    print(f"monitoring port={port} seconds={args.seconds} expected=0x{expected:04X}{expected_mask_text}")
    with serial.Serial(port, 115200, timeout=0.1) as ser:
        # Baudrate is ignored by USB CDC firmware but keeps Windows serial APIs happy.
        while time.monotonic() - start < args.seconds:
            data = ser.read(4096)
            if data:
                buf.extend(data)
            for typ, payload in iter_frames(buf):
                if typ == TYPE_DECODED and len(payload) in (16, 18):
                    if len(payload) == 18:
                        word, count, tick_us, edge_s, raw_mask, stable_mask, levels, flags = struct.unpack(
                            "<HIIIBBBB", payload
                        )
                    else:
                        word, count, tick_us, edge_s, levels, flags = struct.unpack("<HIIIBB", payload)
                        raw_mask = (
                            (1 if word & 0x0010 else 0)
                            | (2 if word & 0x0080 else 0)
                            | (4 if word & 0x0400 else 0)
                            | (8 if word & 0x2000 else 0)
                        )
                        stable_mask = raw_mask
                    words[word] += 1
                    raw_masks[raw_mask] += 1
                    stable_masks[stable_mask] += 1
                    decoded_frames = count
                    edge_count_s = edge_s
                    now = time.monotonic()
                    if now - last_print >= 0.5:
                        last_print = now
                        levels_text = f"S/V/G={levels & 1}/{(levels >> 1) & 1}/{(levels >> 2) & 1}"
                        print(
                            f"t={tick_us / 1_000_000:7.3f}s decoded_count={count:5d} "
                            f"edges_S={edge_s:6d} levels {levels_text} flags={flags} "
                            f"raw_mask=0x{raw_mask:X}({decode_presence_mask(raw_mask)}) "
                            f"stable_mask=0x{stable_mask:X}({decode_presence_mask(stable_mask)}) "
                            f"{decode_word(word)}"
                        )

    print("\nobserved words:")
    for word, count in words.most_common():
        marker = " <== expected" if word == expected else ""
        print(f"  0x{word:04X}: {count}{marker}  {decode_word(word)}")

    if raw_masks:
        print("\nobserved raw presence masks:")
        for mask, count in raw_masks.most_common():
            marker = " <== expected" if expected_mask is not None and mask == expected_mask else ""
            print(f"  0x{mask:X}: {count}{marker}  {decode_presence_mask(mask)}")

    if stable_masks:
        print("\nobserved stable presence masks:")
        for mask, count in stable_masks.most_common():
            marker = " <== expected" if expected_mask is not None and mask == expected_mask else ""
            print(f"  0x{mask:X}: {count}{marker}  {decode_presence_mask(mask)}")

    if not words:
        print("RESULT: no decoded USB status frames received")
        return 2

    most_common_word, most_common_count = words.most_common(1)[0]
    if expected_mask is not None:
        most_common_stable_mask, _ = stable_masks.most_common(1)[0]
        if most_common_stable_mask == expected_mask and decoded_frames > 0 and edge_count_s > 0:
            print(f"RESULT: decoded successfully; dominant stable presence mask matches expected 0x{expected_mask:X}.")
            return 0

        print(
            "RESULT: USB decoded frames were received, but the dominant stable presence mask did not match "
            f"expected 0x{expected_mask:X}."
        )
        return 1

    if most_common_word == expected and decoded_frames > 0 and edge_count_s > 0:
        print(f"RESULT: decoded successfully; dominant word matches expected 0x{expected:04X}.")
        return 0

    print(
        "RESULT: USB decoded frames were received, but the dominant word did not match "
        f"expected 0x{expected:04X}."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
