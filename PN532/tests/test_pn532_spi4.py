#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PN532 SPI4 minimal probe — firmware version + card UID read.

Usage:
  python3 tests/test_pn532_spi4.py --device /dev/spidev4.0 --firmware-only --debug
  python3 tests/test_pn532_spi4.py --device /dev/spidev4.0 --timeout 30
"""

from __future__ import annotations

import argparse
import time


# ═══ Minimal PN532 SPI driver ═══════════════════════════════════════

SPI_DATA_WRITE = 0x01
SPI_STATUS_READ = 0x02
SPI_DATA_READ = 0x03

PN532_PREAMBLE = bytes([0x00, 0x00, 0xFF])
PN532_HOST_TO_PN532 = 0xD4
PN532_PN532_TO_HOST = 0xD5
PN532_ACK = bytes([0x00, 0x00, 0xFF, 0x00, 0xFF, 0x00])

CMD_GET_FIRMWARE_VERSION = 0x02
CMD_SAM_CONFIGURATION = 0x14
CMD_IN_LIST_PASSIVE_TARGET = 0x4A


class PN532_SPI:
    def __init__(
        self,
        device: str = "/dev/spidev4.0",
        speed_hz: int = 100_000,
        mode: int = 0,
        lsbfirst: bool = True,
        debug: bool = False,
    ):
        import spidev
        self.spi = spidev.SpiDev()
        self.spi.open(*(self._parse_device(device)))
        self.spi.max_speed_hz = speed_hz
        self.spi.mode = mode
        self.spi.bits_per_word = 8
        if hasattr(self.spi, "lsbfirst"):
            self.spi.lsbfirst = lsbfirst
        self.debug = debug

    @staticmethod
    def _parse_device(dev: str):
        """Parse '/dev/spidev4.0' → (4, 0)."""
        import re
        m = re.search(r'spidev(\d+)\.(\d+)', dev)
        if m:
            return int(m.group(1)), int(m.group(2))
        raise ValueError(f"cannot parse SPI device: {dev}")

    def _log(self, msg: str):
        if self.debug:
            print(f"  [SPI] {msg}")

    def _xfer(self, data: list[int] | bytes) -> list[int]:
        return self.spi.xfer2(list(data))

    # ── low-level ────────────────────────────────────────────────

    def write_frame(self, frame: bytes):
        """Write a PN532 frame via SPI DATA WRITE (0x01)."""
        payload = bytes([SPI_DATA_WRITE]) + frame
        self._log(f"WRITE: {payload.hex(' ')}")
        self._xfer(payload)

    def read_status(self) -> int:
        """Read SPI status byte (0x02)."""
        result = self._xfer([SPI_STATUS_READ, 0x00])
        self._log(f"STATUS raw: {result}")
        return result[1]

    def read_data(self, n: int) -> bytes:
        """Read n bytes via SPI DATA READ (0x03)."""
        out = [SPI_DATA_READ] + [0x00] * n
        result = self._xfer(out)
        return bytes(result[1:])  # skip status byte

    def wait_ready(self, timeout: float = 1.0) -> bool:
        """Poll status until 0x01 (ready) or timeout."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            st = self.read_status()
            if st == 0x01:
                return True
            time.sleep(0.001)
        return False

    def sync_bus(self):
        """Drain stale SPI bytes before sending a PN532 command."""
        for _ in range(5):
            self.read_status()
            self.read_data(7)
            time.sleep(0.05)

    # ── PN532 framing ────────────────────────────────────────────

    def _send_command(self, cmd: int, params: list[int] = None) -> bytes:
        """Build and send a PN532 command frame, return raw response."""
        params = params or []
        self.sync_bus()
        body = bytes([PN532_HOST_TO_PN532, cmd] + params)
        # checksum: sum of body bytes, negated, masked to 8 bits
        csum = (-sum(body)) & 0xFF
        frame = PN532_PREAMBLE + bytes([len(body) + 1]) + bytes([(-len(body) - 1) & 0xFF]) + body + bytes([csum]) + bytes([0x00])
        self.write_frame(frame)

        # Wait for ACK
        if not self.wait_ready(1.0):
            raise TimeoutError("PN532 not ready after command")
        ack = self.read_data(len(PN532_ACK))
        self._log(f"ACK raw: {ack.hex(' ')}")
        if ack != PN532_ACK:
            raise RuntimeError(f"expected ACK, got {ack.hex(' ')}")

        # Read response
        if not self.wait_ready(1.0):
            raise TimeoutError("PN532 not ready for response")
        # Read preamble + len + lcs
        hdr = self.read_data(5)
        self._log(f"HDR: {hdr.hex(' ')}")
        resp_len = hdr[3] if len(hdr) >= 4 else 0
        if resp_len > 0:
            body_data = self.read_data(resp_len + 2)  # + checksum + postamble
            self._log(f"BODY: {body_data.hex(' ')}")
            # body_data[0] should be D5, then cmd+1, then data, then checksum
            return bytes([hdr[3]]) + body_data
        return hdr + b''

    def call_function(self, cmd: int, params: list[int] = None, timeout: float = 1.0) -> list[int]:
        """Send PN532 command and parse response."""
        raw = self._send_command(cmd, params)
        # raw: [resp_len, PN532_PN532_TO_HOST, cmd+1, ...data..., csum, postamble]
        if len(raw) < 3:
            raise RuntimeError(f"response too short: {raw.hex(' ')}")
        if raw[1] != PN532_PN532_TO_HOST:
            raise RuntimeError(f"unexpected response direction: {raw[1]:02X}")
        if raw[2] != cmd + 1:
            raise RuntimeError(f"unexpected response cmd: {raw[2]:02X}, expected {cmd + 1:02X}")
        return list(raw[3:-2])  # strip cmd+1, checksum, postamble

    # ── high-level ───────────────────────────────────────────────

    def get_firmware_version(self):
        data = self.call_function(CMD_GET_FIRMWARE_VERSION)
        # data: ic, ver, rev, support
        return {"ic": data[0], "ver": data[1], "rev": data[2], "support": data[3]}

    def sam_configuration(self):
        """Normal mode, timeout 1s."""
        self.call_function(CMD_SAM_CONFIGURATION, [0x01, 0x14, 0x01])

    def begin(self):
        fw = self.get_firmware_version()
        print(f"[INFO] PN532 detected: IC=0x{fw['ic']:02X}, Firmware v{fw['ver']}.{fw['rev']}, Support=0x{fw['support']:02X}")
        self.sam_configuration()
        print("[INFO] PN532 initialized successfully (SPI).")

    def read_passive_target_id(self, timeout: float = 1.0) -> list[int] | None:
        """InListPassiveTarget (1 target, type 106A). Returns UID bytes or None."""
        try:
            data = self.call_function(CMD_IN_LIST_PASSIVE_TARGET, [0x01, 0x00], timeout=timeout)
        except Exception:
            return None
        # data[0] = NbTg
        if data[0] < 1:
            return None
        # Parse target data: TAG(1) + LEN(1) + ... for each SENS_RES, SEL_RES, NFCID...
        idx = 1
        uid = None
        while idx < len(data):
            tag = data[idx]
            tag_len = data[idx + 1]
            idx += 2
            if tag == 0x04:  # NFCID
                uid = data[idx:idx + tag_len]
            idx += tag_len
        return uid

    def close(self):
        self.spi.close()


# ═══ Main ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="PN532 SPI minimal probe")
    parser.add_argument("--device", default="/dev/spidev4.0")
    parser.add_argument("--speed", type=int, default=100000)
    parser.add_argument("--mode", type=int, default=0)
    parser.add_argument("--msb-first", action="store_true", help="disable PN532 SPI LSB-first transfer")
    parser.add_argument("--timeout", type=int, default=0, help="card read timeout (0 = firmware only)")
    parser.add_argument("--firmware-only", action="store_true")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    pn532 = PN532_SPI(
        device=args.device,
        speed_hz=args.speed,
        mode=args.mode,
        lsbfirst=not args.msb_first,
        debug=args.debug,
    )

    try:
        print("=" * 60)
        print("PN532 SPI Probe")
        print("=" * 60)
        print(f"Device: {args.device}")
        print(f"Speed:  {args.speed} Hz")
        print(f"Mode:   {args.mode}")
        print(f"Order:  {'MSB first' if args.msb_first else 'LSB first'}")
        print()

        # ── Firmware ──
        print("--- Firmware check ---")
        pn532.begin()

        if args.firmware_only:
            print("[OK] Firmware check passed.")
            return 0

        # ── Card read ──
        card_timeout = args.timeout or 30
        print(f"--- Card read (timeout={card_timeout}s) ---")
        print("Place card on PN532...")
        deadline = time.monotonic() + card_timeout
        dots = 0
        while time.monotonic() < deadline:
            uid = pn532.read_passive_target_id(timeout=0.5)
            if uid:
                uid_hex = ":".join(f"{b:02X}" for b in uid)
                print(f"\n[OK] UID: {uid_hex}")
                return 0
            print("." if dots % 40 == 0 else "", end="", flush=True)
            dots += 1
            time.sleep(0.2)

        print()
        print("[FAIL] No card detected within timeout.")
        return 2

    except Exception as exc:
        print(f"[FAIL] {exc}")
        return 1
    finally:
        pn532.close()


if __name__ == "__main__":
    raise SystemExit(main())
