from __future__ import annotations

import argparse
import struct
import time
from pathlib import Path

import serial


EDGE_MAGIC = 0xE1
STATUS_MAGIC = 0x5A
EDGE_SIZE = 16
STATUS_SIZE = 24


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture STM32 three-wire sniffer binary stream.")
    parser.add_argument("--port", required=True, help="Serial port, e.g. COM8.")
    parser.add_argument("--baud", type=int, default=1_000_000, help="UART baudrate.")
    parser.add_argument("--seconds", type=float, default=60.0, help="Capture duration.")
    parser.add_argument("--out", type=Path, default=None, help="Output .bin path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    out = args.out or Path(f"capture_three_wire_{time.strftime('%Y%m%d_%H%M%S')}.bin")
    out.parent.mkdir(parents=True, exist_ok=True)

    start = time.monotonic()
    buf = bytearray()
    edge_counts = [0, 0, 0]
    last_print = 0.0

    with serial.Serial(args.port, args.baud, timeout=0.1) as ser, out.open("wb") as f:
        print(f"capturing {args.port} at {args.baud}, output={out}")
        while time.monotonic() - start < args.seconds:
            data = ser.read(4096)
            if data:
                f.write(data)
                buf.extend(data)

            while buf:
                magic = buf[0]
                if magic == EDGE_MAGIC and len(buf) >= EDGE_SIZE:
                    rec = bytes(buf[:EDGE_SIZE])
                    del buf[:EDGE_SIZE]
                    _, ch, level, flags, dt_us, tick_us, seq, ec_low = struct.unpack("<BBBBIIHH", rec)
                    if ch < 3:
                        edge_counts[ch] += 1
                    if flags:
                        print(f"warning: edge flags={flags} ch={ch} seq={seq} tick={tick_us}")
                elif magic == STATUS_MAGIC and len(buf) >= STATUS_SIZE:
                    rec = bytes(buf[:STATUS_SIZE])
                    del buf[:STATUS_SIZE]
                    _, levels, flags, _, tick_us, c0, c1, c2, dropped = struct.unpack("<BBBBIIIII", rec)
                    now = time.monotonic()
                    if now - last_print >= 0.5:
                        last_print = now
                        print(
                            f"t={tick_us/1_000_000:8.3f}s "
                            f"levels S/V/G={levels & 1}/{(levels >> 1) & 1}/{(levels >> 2) & 1} "
                            f"edges S/V/G={c0}/{c1}/{c2} dropped={dropped} flags={flags}"
                        )
                else:
                    # Resync to the next plausible packet start.
                    next_edge = buf.find(bytes([EDGE_MAGIC]), 1)
                    next_status = buf.find(bytes([STATUS_MAGIC]), 1)
                    candidates = [x for x in (next_edge, next_status) if x >= 0]
                    if not candidates:
                        del buf[:]
                    else:
                        del buf[: min(candidates)]

    print(f"done. saved={out}")
    print(f"observed edge packets S/V/G={edge_counts[0]}/{edge_counts[1]}/{edge_counts[2]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
