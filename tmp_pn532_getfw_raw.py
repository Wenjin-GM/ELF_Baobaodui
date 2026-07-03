#!/usr/bin/env python3
import argparse
import re
import time

import spidev


def parse_device(device):
    match = re.search(r"spidev(\d+)\.(\d+)", device)
    if not match:
        raise ValueError(device)
    return int(match.group(1)), int(match.group(2))


def hx(data):
    return " ".join(f"{x:02X}" for x in data)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default="/dev/spidev4.0")
    parser.add_argument("--speed", type=int, default=100000)
    parser.add_argument("--mode", type=int, default=0)
    parser.add_argument("--lsbfirst", action="store_true")
    parser.add_argument("--preflush", type=int, default=0)
    parser.add_argument("--force-read", action="store_true")
    parser.add_argument("--cshigh", action="store_true")
    parser.add_argument("--no-cs", action="store_true")
    args = parser.parse_args()

    spi = spidev.SpiDev()
    spi.open(*parse_device(args.device))
    spi.max_speed_hz = args.speed
    spi.mode = args.mode
    spi.bits_per_word = 8
    if hasattr(spi, "lsbfirst"):
        spi.lsbfirst = bool(args.lsbfirst)
    if hasattr(spi, "cshigh"):
        spi.cshigh = bool(args.cshigh)
    if hasattr(spi, "no_cs"):
        spi.no_cs = bool(args.no_cs)

    def xfer(data):
        out = spi.xfer2(list(data))
        print(f"TX {hx(data)} -> RX {hx(out)}")
        return out

    try:
        print(
            f"device={args.device} speed={args.speed} mode={args.mode} "
            f"lsbfirst={args.lsbfirst} cshigh={args.cshigh} no_cs={args.no_cs}"
        )
        for i in range(args.preflush):
            xfer([0x02, 0x00])
            xfer([0x03, 0, 0, 0, 0, 0, 0, 0, 0])
            time.sleep(0.05)

        frame = [0x01, 0x00, 0x00, 0xFF, 0x03, 0xFD, 0xD4, 0x02, 0x2A, 0x00]
        xfer(frame)

        ready = False
        for i in range(40):
            status = xfer([0x02, 0x00])
            if 0x01 in status:
                print(f"READY at poll {i}")
                ready = True
                break
            time.sleep(0.05)
        if not ready and not args.force_read:
            print("NO_READY")
            return 1

        ack = xfer([0x03] + [0x00] * 8)
        print("ACK_READ", hx(ack))

        ready = False
        for i in range(40):
            status = xfer([0x02, 0x00])
            if 0x01 in status:
                print(f"RESP_READY at poll {i}")
                ready = True
                break
            time.sleep(0.05)
        if not ready and not args.force_read:
            print("NO_RESP_READY")
            return 2

        header = xfer([0x03] + [0x00] * 8)
        print("RESP_HEAD", hx(header))
        body = xfer([0x03] + [0x00] * 16)
        print("RESP_BODY", hx(body))
        return 0
    finally:
        spi.close()


if __name__ == "__main__":
    raise SystemExit(main())
