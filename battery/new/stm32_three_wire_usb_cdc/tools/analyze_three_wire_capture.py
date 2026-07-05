from __future__ import annotations

import argparse
import struct
from collections import Counter
from pathlib import Path


FRAME0 = 0xA5
FRAME1 = 0x5A
TYPE_EDGE = 0xE1
TYPE_STATUS = 0x5A


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze STM32 three-wire sniffer capture.")
    parser.add_argument("capture", type=Path)
    parser.add_argument("--unit-us", type=float, default=1021.0)
    parser.add_argument("--gap-us", type=int, default=10000)
    return parser.parse_args()


def iter_records(data: bytes):
    i = 0
    while i < len(data) - 5:
        if data[i] == FRAME0 and data[i + 1] == FRAME1:
            typ = data[i + 2]
            ln = data[i + 3]
            frame_len = 5 + ln
            if i + frame_len <= len(data):
                payload = data[i + 4 : i + 4 + ln]
                crc = typ ^ ln
                for value in payload:
                    crc ^= value
                if (crc & 0xFF) == data[i + frame_len - 1]:
                    yield typ, payload
                    i += frame_len
                    continue
        i += 1


def decode_pwm_candidate(units: tuple[int, ...]):
    if len(units) < 6:
        return []

    # Common observed form:
    # idle gap, preamble low/high/low = 4/3/3 units, then alternating durations.
    data = units[4:]
    candidates = []
    for offset in (0, 1):
        pairs = list(zip(data[offset::2], data[offset + 1 :: 2]))
        for zero, one in (((1, 2), (2, 1)), ((2, 1), (1, 2))):
            bits = []
            ok = True
            for pair in pairs:
                if pair == zero:
                    bits.append("0")
                elif pair == one:
                    bits.append("1")
                else:
                    bits.append("?")
                    ok = False
            bitstr = "".join(bits)
            candidates.append((offset, zero, one, ok, bitstr))
    return candidates


def bits_to_bytes(bitstr: str, lsb_first: bool) -> list[int]:
    out = []
    if "?" in bitstr:
        return out
    for i in range(0, len(bitstr), 8):
        chunk = bitstr[i : i + 8]
        if len(chunk) < 8:
            break
        if lsb_first:
            chunk = chunk[::-1]
        out.append(int(chunk, 2))
    return out


def main() -> int:
    args = parse_args()
    data = args.capture.read_bytes()

    edges = []
    statuses = []
    for typ, payload in iter_records(data):
        if typ == TYPE_EDGE and len(payload) == 15:
            ch, level, flags = payload[0], payload[1], payload[2]
            dt = struct.unpack_from("<I", payload, 3)[0]
            tick = struct.unpack_from("<I", payload, 7)[0]
            seq = struct.unpack_from("<H", payload, 11)[0]
            if ch == 0:
                edges.append((level, flags, dt, tick, seq))
        elif typ == TYPE_STATUS and len(payload) == 23:
            levels, flags = payload[0], payload[1]
            tick = struct.unpack_from("<I", payload, 3)[0]
            c0 = struct.unpack_from("<I", payload, 7)[0]
            c1 = struct.unpack_from("<I", payload, 11)[0]
            c2 = struct.unpack_from("<I", payload, 15)[0]
            dropped = struct.unpack_from("<I", payload, 19)[0]
            statuses.append((levels, flags, tick, c0, c1, c2, dropped))

    frames = []
    current = []
    for edge in edges:
        dt = edge[2]
        if dt > args.gap_us and current:
            frames.append(current)
            current = []
        current.append(edge)
    if current:
        frames.append(current)

    patterns = Counter()
    for frame in frames:
        units = tuple(round(edge[2] / args.unit_us) for edge in frame)
        levels = "".join(str(edge[0]) for edge in frame)
        patterns[(units, levels)] += 1

    print(f"capture={args.capture}")
    print(f"bytes={len(data)} edge_frames={len(edges)} status_frames={len(statuses)} split_frames={len(frames)}")
    if statuses:
        first = statuses[0]
        last = statuses[-1]
        print(
            "status_first: "
            f"levels S/V/G={first[0]&1}/{(first[0]>>1)&1}/{(first[0]>>2)&1} "
            f"tick_us={first[2]} edges={first[3]}/{first[4]}/{first[5]} dropped={first[6]} flags={first[1]}"
        )
        print(
            "status_last:  "
            f"levels S/V/G={last[0]&1}/{(last[0]>>1)&1}/{(last[0]>>2)&1} "
            f"tick_us={last[2]} edges={last[3]}/{last[4]}/{last[5]} dropped={last[6]} flags={last[1]}"
        )

    print("\nTop normalized frame patterns:")
    for idx, ((units, levels), count) in enumerate(patterns.most_common(8), 1):
        print(f"{idx}. count={count} edges={len(units)}")
        print(f"   units={units}")
        print(f"   levels={levels}")
        for offset, zero, one, ok, bitstr in decode_pwm_candidate(units):
            if ok:
                msb = " ".join(f"{b:02X}" for b in bits_to_bytes(bitstr, lsb_first=False))
                lsb = " ".join(f"{b:02X}" for b in bits_to_bytes(bitstr, lsb_first=True))
                print(f"   candidate offset={offset} zero={zero} one={one} bits={bitstr} msb=[{msb}] lsb=[{lsb}]")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
