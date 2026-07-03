#!/usr/bin/env python3
import argparse
import re
import time

import spidev


def parse_device(device: str) -> tuple[int, int]:
    match = re.search(r"spidev(\d+)\.(\d+)", device)
    if not match:
        raise ValueError(f"cannot parse SPI device: {device}")
    return int(match.group(1)), int(match.group(2))


def xfer_once(device: str, speed: int, mode: int, lsbfirst: bool) -> None:
    bus, cs = parse_device(device)
    spi = spidev.SpiDev()
    try:
        spi.open(bus, cs)
        spi.max_speed_hz = speed
        spi.mode = mode
        spi.bits_per_word = 8
        if hasattr(spi, "lsbfirst"):
            spi.lsbfirst = lsbfirst
        print(f"--- {device} speed={speed} mode={mode} lsbfirst={lsbfirst} ---")
        for i in range(5):
            status = spi.xfer2([0x02, 0x00])
            data = spi.xfer2([0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
            print(f"status[{i}]={status} data={data}")
            time.sleep(0.05)

        # GetFirmwareVersion command frame: 00 00 FF 03 FD D4 02 2A 00
        write = [0x01, 0x00, 0x00, 0xFF, 0x03, 0xFD, 0xD4, 0x02, 0x2A, 0x00]
        print(f"write={write}")
        print(f"write_resp={spi.xfer2(write)}")
        for i in range(20):
            status = spi.xfer2([0x02, 0x00])
            print(f"post_status[{i}]={status}")
            if len(status) > 1 and status[1] == 0x01:
                ack = spi.xfer2([0x03] + [0x00] * 8)
                print(f"ack_read={ack}")
                break
            time.sleep(0.05)
    except Exception as exc:
        print(f"ERROR {device} speed={speed} mode={mode} lsbfirst={lsbfirst}: {exc}")
    finally:
        try:
            spi.close()
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--devices", nargs="+", default=["/dev/spidev4.0"])
    parser.add_argument("--speeds", nargs="+", type=int, default=[100000, 500000, 1000000])
    args = parser.parse_args()

    for device in args.devices:
        for speed in args.speeds:
            for mode in range(4):
                for lsbfirst in (False, True):
                    xfer_once(device, speed, mode, lsbfirst)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
