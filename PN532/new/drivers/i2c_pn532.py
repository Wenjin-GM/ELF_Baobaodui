#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PN532 NFC Module — I2C Driver for RK3588 / Linux
=================================================

Target hardware:
    - SoC:       Rockchip RK3588 (ELF 2)
    - NFC chip:  NXP PN532 (I2C mode)
    - I2C bus:   /dev/i2c-4
    - Address:   0x24

Dependencies:
    - smbus2  (pip3 install smbus2)
    - Python ≥ 3.7

Reference:
    - 08-外设/PN532/NFC_I2C测试指南.md
    - NXP PN532 User Manual (public datasheet)

Author: 宝宝队
License: MIT
"""

import time
import smbus2


# ---------------------------------------------------------------------------
# PN532 I2C Driver
# ---------------------------------------------------------------------------

class PN532_I2C:
    """PN532 NFC controller driver over I2C (smbus2)."""

    # ── I2C constants ──────────────────────────────────────────────────
    PN532_I2C_ADDRESS = 0x24          # 7-bit I2C address (fixed in hardware)

    # ── TFI (Transport Frame Indicator) ─────────────────────────────────
    HOST_TO_PN532   = 0xD4            # Direction: Host → PN532
    PN532_TO_HOST   = 0xD5            # Direction: PN532 → Host

    # ── ACK packet (PN532 → Host) ──────────────────────────────────────
    ACK_PACKET = bytes([0x00, 0x00, 0xFF, 0x00, 0xFF, 0x00])

    # ── Normal-mode command codes ──────────────────────────────────────
    CMD_GET_FIRMWARE_VERSION  = 0x02  # → IC + Ver + Rev + Support flags
    CMD_SAM_CONFIGURATION     = 0x14  # → configure SAM (normal mode)
    CMD_IN_LIST_PASSIVE_TARGET = 0x4A # → poll for ISO14443A / FeliCa cards
    CMD_IN_DATA_EXCHANGE      = 0x40  # → talk to an activated card
    CMD_RF_CONFIGURATION      = 0x32  # → tune RF retries / field

    # ── MIFARE Classic commands (sent through InDataExchange) ──────────
    MIFARE_AUTH_KEY_A = 0x60
    MIFARE_AUTH_KEY_B = 0x61
    MIFARE_READ       = 0x30          # read one 16-byte block
    MIFARE_WRITE      = 0xA0          # write one 16-byte block

    # ── Baud-rate constants for InListPassiveTarget ────────────────────
    BR_ISO14443A_MIFARE = 0x00        # 106 kbps, Type A

    def __init__(self, bus=4, address=PN532_I2C_ADDRESS, debug=False):
        """
        Parameters
        ----------
        bus : int
            I2C bus number (default 4 → /dev/i2c-4 on RK3588 ELF 2).
        address : int
            7-bit I2C address (default 0x24, factory-set on PN532).
        debug : bool
            Print low-level frame hex dumps when True.
        """
        self.bus_num = bus
        self.address = address
        self.debug = debug
        self._bus = smbus2.SMBus(bus)

    # ── logging helper ─────────────────────────────────────────────────
    def _log(self, msg: str) -> None:
        if self.debug:
            print(f"[PN532] {msg}")

    # -------------------------------------------------------------------
    # Low-level I2C primitives
    # -------------------------------------------------------------------

    def _i2c_write(self, data: bytes) -> None:
        """Write raw bytes to the PN532 I2C address."""
        self._log(f"I2C TX → {' '.join(f'{b:02X}' for b in data)}")
        msg = smbus2.i2c_msg.write(self.address, list(data))
        self._bus.i2c_rdwr(msg)

    def _i2c_read(self, count: int) -> list:
        """Read *count* raw bytes from the PN532 I2C address."""
        msg = smbus2.i2c_msg.read(self.address, count)
        self._bus.i2c_rdwr(msg)
        data = list(msg)
        self._log(f"I2C RX ← {' '.join(f'{b:02X}' for b in data)}")
        return data

    # -------------------------------------------------------------------
    # PN532 status polling
    # -------------------------------------------------------------------

    def _read_status(self) -> int:
        """Return the 1-byte status from PN532 (0x01 = ready, else busy)."""
        try:
            data = self._i2c_read(1)
            return data[0] if data else 0xFF
        except OSError:
            return 0xFF

    def _wait_ready(self, timeout: float = 1.0) -> bool:
        """Block until PN532 signals *ready* (status == 0x01)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._read_status() == 0x01:
                return True
            time.sleep(0.002)          # 2 ms polling interval
        self._log(f"timeout waiting for ready (> {timeout:.1f}s)")
        return False

    # -------------------------------------------------------------------
    # PN532 frame helpers
    # -------------------------------------------------------------------

    @staticmethod
    def _build_frame(data: list) -> list:
        """Wrap payload *data* in a complete PN532 frame.

        Frame layout (I2C mode)
        -----------------------
        [PREAMBLE] [START0] [START1] [LEN] [LCS] [TFI] [CMD] [DATA…] [DCS] [POST]

        · PREAMBLE  0x00              — always sent on I2C
        · START     0x00 0xFF         — frame sync
        · LEN       payload length    — TFI + CMD + DATA  (≥ 2)
        · LCS       ~LEN + 1          — length checksum: (LEN + LCS) % 256 == 0
        · DCS       ~SUM + 1          — data checksum: (sum(DATA) + DCS) % 256 == 0
        · POST      0x00              — postamble

        Returns
        -------
        list[int]
            Full frame ready to send via I2C.
        """
        length = len(data)
        lcs = (0x100 - length) & 0xFF
        dcs = (0x100 - (sum(data) & 0xFF)) & 0xFF
        return [0x00, 0x00, 0xFF, length, lcs] + list(data) + [dcs, 0x00]

    @staticmethod
    def _find_frame_start(data: list) -> int:
        """Return the index of the first ``00 00 FF`` preamble in *data*,
        or -1 if not found."""
        for i in range(len(data) - 2):
            if data[i] == 0x00 and data[i + 1] == 0x00 and data[i + 2] == 0xFF:
                return i
        return -1

    def _read_ack(self) -> bool:
        """Read 6 bytes and verify they match the PN532 ACK packet."""
        ack = bytes(self._i2c_read(6))
        if ack == self.ACK_PACKET:
            self._log("ACK received")
            return True
        self._log(f"bad ACK: {ack.hex(' ').upper()}")
        return False

    def _read_response_frame(self, max_len: int = 64) -> list | None:
        """Read and validate a PN532 response frame.

        Returns the **payload** (TFI + CMD + DATA…) on success,
        or ``None`` on any checksum / framing error.
        """
        raw = self._i2c_read(max_len)
        if not raw:
            return None

        # Locate the ``00 00 FF`` sync sequence
        start = self._find_frame_start(raw)
        if start < 0:
            self._log("frame sync 00 00 FF not found in response")
            return None

        data = raw[start:]
        if len(data) < 7:
            self._log("response too short for a valid frame")
            return None

        length = data[3]
        lcs    = data[4]

        # Length == 0 + specific pattern → ACK packet snuck in
        if length == 0x00:
            candidate = bytes(data[:6])
            if candidate == self.ACK_PACKET:
                self._log("received ACK where response frame expected")
            return None

        # Validate length checksum
        if ((length + lcs) & 0xFF) != 0x00:
            self._log(f"LCS mismatch: LEN=0x{length:02X} LCS=0x{lcs:02X}")
            return None

        frame_total = length + 7                 # header(5) + payload + DCS + POST
        if len(data) < frame_total:
            self._log(f"incomplete frame: need {frame_total} bytes, have {len(data)}")
            return None

        frame_data = data[5 : 5 + length]        # TFI + CMD + DATA…
        dcs        = data[5 + length]
        postamble  = data[6 + length]

        # Validate data checksum
        if ((sum(frame_data) + dcs) & 0xFF) != 0x00:
            self._log(f"DCS mismatch for data: {' '.join(f'{b:02X}' for b in frame_data)}")
            return None

        if postamble != 0x00:
            self._log(f"unexpected postamble 0x{postamble:02X} (expected 0x00)")

        self._log(f"response payload: {' '.join(f'{b:02X}' for b in frame_data)}")
        return frame_data

    # -------------------------------------------------------------------
    # Command dispatch
    # -------------------------------------------------------------------

    def send_command(self, command: int, params: list | None = None,
                     timeout: float = 1.0) -> list | None:
        """Send a PN532 command and return the response *payload*.

        Parameters
        ----------
        command : int
            Command byte (e.g. ``CMD_GET_FIRMWARE_VERSION``).
        params : list[int] | None
            Optional command parameters.
        timeout : float
            Seconds to wait for each of ACK + response.

        Returns
        -------
        list[int] | None
            Response payload (from TFI onwards) on success, ``None`` on failure.
        """
        if params is None:
            params = []

        payload = [self.HOST_TO_PN532, command] + params
        frame = self._build_frame(payload)

        # ── Send ──
        try:
            self._i2c_write(bytes(frame))
        except OSError as exc:
            self._log(f"I2C write error: {exc}")
            return None

        # ── Wait for ACK ──
        if not self._wait_ready(timeout):
            self._log(f"no ACK ready for command 0x{command:02X}")
            return None

        if not self._read_ack():
            return None

        # ── Wait for Response ──
        if not self._wait_ready(timeout):
            self._log(f"no response ready for command 0x{command:02X}")
            return None

        frame_data = self._read_response_frame()
        if frame_data is None:
            return None

        if len(frame_data) < 2:
            self._log("response payload too short (need at least TFI + CMD)")
            return None

        tfi      = frame_data[0]
        resp_cmd = frame_data[1]
        data     = frame_data[2:]

        if tfi != self.PN532_TO_HOST:
            self._log(f"unexpected TFI 0x{tfi:02X}, expected 0x{self.PN532_TO_HOST:02X}")
            return None

        expected_cmd = (command + 1) & 0xFF
        if resp_cmd != expected_cmd:
            self._log(
                f"unexpected response command 0x{resp_cmd:02X}, "
                f"expected 0x{expected_cmd:02X}"
            )
            return None

        return data

    # -------------------------------------------------------------------
    # Wake-up sequence
    # -------------------------------------------------------------------

    def _wakeup(self) -> None:
        """Send a dummy I2C write to wake PN532 from low-power state.

        Some PN532 modules (especially CH340-based USB bridges) ignore
        the first command after power-on; this sequence ensures the chip
        is listening before we send real frames.
        """
        self._log("waking PN532 …")
        try:
            self._i2c_write(bytes([0x00]))
        except OSError:
            pass
        time.sleep(0.01)

    # -------------------------------------------------------------------
    #  High-level public API
    # -------------------------------------------------------------------

    # ── Init / self-test ───────────────────────────────────────────────

    def begin(self) -> bool:
        """Initialise the PN532 and verify communication.

        Returns ``True`` if the chip responds with a valid firmware
        version and SAM configuration succeeds.
        """
        self._wakeup()

        fw = self.get_firmware_version()
        if fw is None:
            # One retry — sometimes the first command after wake-up is lost
            self._wakeup()
            time.sleep(0.05)
            fw = self.get_firmware_version()

        if fw is None:
            print("[ERROR] Cannot communicate with PN532. Check wiring and I2C address.")
            return False

        print(
            f"[INFO] PN532 detected: "
            f"IC=0x{fw['ic']:02X}, "
            f"Firmware v{fw['ver']}.{fw['rev']}, "
            f"Support=0x{fw['support']:02X}"
        )

        if not self.sam_configuration():
            print("[ERROR] SAM configuration failed!")
            return False

        print("[INFO] PN532 initialized successfully.")
        return True

    def get_firmware_version(self) -> dict | None:
        """Read the PN532 firmware version.

        Returns
        -------
        dict | None
            ``{"ic": int, "ver": int, "rev": int, "support": int}``
            or ``None`` on failure.
        """
        resp = self.send_command(self.CMD_GET_FIRMWARE_VERSION, timeout=1.0)
        if resp is not None and len(resp) >= 4:
            return {
                "ic":      resp[0],
                "ver":     resp[1],
                "rev":     resp[2],
                "support": resp[3],
            }
        return None

    # ── SAM configuration ──────────────────────────────────────────────

    def sam_configuration(self, mode: int = 0x01,
                          timeout_50ms: int = 0x14,
                          irq: bool = False) -> bool:
        """Configure the PN532 Security Access Module (SAM).

        Parameters
        ----------
        mode : int
            0x01 = normal mode; 0x02 = virtual card; 0x03 = wired card; 0x04 = dual card.
        timeout_50ms : int
            SAM timeout in units of 50 ms (default 0x14 → 1.0 s).
        irq : bool
            Use IRQ pin for card detection (default False).

        Returns
        -------
        bool
            ``True`` on success.
        """
        params = [mode, timeout_50ms]
        if irq:
            params.append(0x01)
        resp = self.send_command(self.CMD_SAM_CONFIGURATION, params, timeout=1.0)
        return resp is not None

    # ── RF retries ─────────────────────────────────────────────────────

    def set_rf_retries(self, max_retries: int = 0x01) -> bool:
        """Configure the number of retries for RF communication.

        Parameters
        ----------
        max_retries : int
            Maximum retry count (0x00 = no retry, 0x01 … 0xFE).

        Returns
        -------
        bool
            ``True`` on success.
        """
        # RFCfg command 0x05 = MAX_RETRIES
        params = [0x05, 0x01, 0x01, max_retries]
        resp = self.send_command(self.CMD_RF_CONFIGURATION, params, timeout=1.0)
        return resp is not None

    # ── Card polling ───────────────────────────────────────────────────

    def read_passive_target_id(self,
                               card_baud: int = BR_ISO14443A_MIFARE,
                               timeout: float = 2.0) -> list | None:
        """Poll for an ISO14443A / MIFARE card and return its UID.

        Parameters
        ----------
        card_baud : int
            Baud-rate constant (default ``BR_ISO14443A_MIFARE`` = 0x00).
        timeout : float
            Seconds to wait before giving up (passed to ``send_command``).

        Returns
        -------
        list[int] | None
            UID as a list of bytes (e.g. ``[0x8A, 0x3B, 0x12, 0xE4]``),
            or ``None`` if no card is found.
        """
        # MaxTg=1 → return after first card
        resp = self.send_command(
            self.CMD_IN_LIST_PASSIVE_TARGET,
            [0x01, card_baud],
            timeout=timeout,
        )

        if resp is None:
            return None

        if len(resp) < 6:
            self._log("InListPassiveTarget response too short")
            return None

        nb_targets = resp[0]
        if nb_targets == 0:
            return None

        # For ISO14443A: resp layout
        #   [0] NbTg  [1] Tg  [2:4] SENS_RES  [4] SEL_RES  [5] UIDLen  [6:…] UID
        uid_len = resp[5]
        if len(resp) < 6 + uid_len:
            self._log(f"UID truncated: need {uid_len} bytes, have {len(resp) - 6}")
            return None

        return resp[6 : 6 + uid_len]

    # ── MIFARE Classic authentication ──────────────────────────────────

    def mifare_authenticate_block(self,
                                  uid: list,
                                  block_number: int,
                                  key: list,
                                  key_type: str = "A") -> bool:
        """Authenticate a MIFARE Classic block using Key A or Key B.

        Parameters
        ----------
        uid : list[int]
            Card UID (at least 4 bytes).
        block_number : int
            Absolute block number to authenticate (0 … 63 for 1K, 0 … 255 for 4K).
        key : list[int]
            6-byte key (e.g. ``[0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]``).
        key_type : str
            ``"A"`` or ``"B"``.

        Returns
        -------
        bool
            ``True`` if authentication succeeded (card returned 0x00).
        """
        if uid is None or len(uid) < 4:
            print("[ERROR] UID must be at least 4 bytes")
            return False

        if len(key) != 6:
            print("[ERROR] MIFARE key must be exactly 6 bytes")
            return False

        auth_cmd = self.MIFARE_AUTH_KEY_A if key_type.upper() == "A" \
                   else self.MIFARE_AUTH_KEY_B

        # InDataExchange payload: TgNum=1, AuthCmd, BlockNum, Key[6], UID[4]
        params = [0x01, auth_cmd, block_number] + list(key) + list(uid[:4])

        resp = self.send_command(self.CMD_IN_DATA_EXCHANGE, params, timeout=1.0)
        if resp is not None and len(resp) > 0 and resp[0] == 0x00:
            return True
        return False

    # ── MIFARE Classic read ────────────────────────────────────────────

    def mifare_read_block(self, block_number: int) -> bytes | None:
        """Read one 16-byte block from an authenticated MIFARE Classic card.

        .. note::
            You must call :meth:`mifare_authenticate_block` for the
            containing sector before reading.

        Parameters
        ----------
        block_number : int
            Absolute block number (0 … 63 for 1K).

        Returns
        -------
        bytes | None
            16 bytes of block data, or ``None`` on failure.
        """
        params = [0x01, self.MIFARE_READ, block_number]
        resp = self.send_command(self.CMD_IN_DATA_EXCHANGE, params, timeout=1.0)

        if resp is not None and len(resp) >= 17 and resp[0] == 0x00:
            return bytes(resp[1:17])
        return None

    # ── MIFARE Classic write ───────────────────────────────────────────

    def mifare_write_block(self, block_number: int, data: bytes) -> bool:
        """Write one 16-byte block to an authenticated MIFARE Classic card.

        .. warning::
            Writing to a sector trailer (every 4th block) changes the
            access bits and keys — doing so incorrectly can brick the card.

        .. note::
            You must call :meth:`mifare_authenticate_block` for the
            containing sector before writing.

        Parameters
        ----------
        block_number : int
            Absolute block number.
        data : bytes
            Exactly 16 bytes to write.

        Returns
        -------
        bool
            ``True`` if the card acknowledged the write.
        """
        if len(data) != 16:
            print("[ERROR] MIFARE write data must be exactly 16 bytes")
            return False

        params = [0x01, self.MIFARE_WRITE, block_number] + list(data)
        resp = self.send_command(self.CMD_IN_DATA_EXCHANGE, params, timeout=1.0)

        if resp is not None and len(resp) > 0 and resp[0] == 0x00:
            return True
        return False

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def format_uid(uid: list | None) -> str:
        """Format a UID list as a human-readable hex string.

        >>> PN532_I2C.format_uid([0x8A, 0x3B, 0x12, 0xE4])
        '8A 3B 12 E4'
        """
        if uid is None:
            return "None"
        return " ".join(f"{b:02X}" for b in uid)

    # ── Cleanup ────────────────────────────────────────────────────────

    def close(self) -> None:
        """Release the I2C bus.  Safe to call multiple times."""
        try:
            self._bus.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Project integration helper — NFC identity authentication
# ---------------------------------------------------------------------------

class NFCAuth:
    """Convenience wrapper for project identity-authentication workflows.

    Usage::

        auth = NFCAuth(authorized_uids={"8A3B12E4", "12345678"})
        uid_str, allowed = auth.poll_and_auth()
        if allowed:
            print(f"Authorized: {uid_str}")
            # → GPIO unlock …
    """

    def __init__(self, authorized_uids: set | None = None, bus: int = 4):
        """
        Parameters
        ----------
        authorized_uids : set[str] | None
            Set of hex UID strings (no spaces) that are allowed access.
        bus : int
            I2C bus number.
        """
        self._nfc = PN532_I2C(bus=bus)
        self.authorized_uids = authorized_uids or set()

    def begin(self) -> bool:
        """Initialise the underlying PN532.  Call once after construction."""
        return self._nfc.begin()

    def poll_and_auth(self, timeout: float = 5.0) -> tuple[str | None, bool]:
        """Block until a card is presented, then check its UID against the
        authorised set.

        Parameters
        ----------
        timeout : float
            Seconds to wait for a card.

        Returns
        -------
        tuple[str | None, bool]
            ``(uid_hex_string, is_authorized)``.  If no card is detected
            within *timeout*, returns ``(None, False)``.
        """
        uid = self._nfc.read_passive_target_id(timeout=timeout)
        if uid is None:
            return None, False

        uid_str = "".join(f"{b:02X}" for b in uid)
        is_auth = uid_str in self.authorized_uids
        return uid_str, is_auth

    def close(self) -> None:
        """Release the I2C bus."""
        self._nfc.close()


# ---------------------------------------------------------------------------
# Quick self-test (run when file is executed directly)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("PN532 I2C Driver — Self-Test")
    print("=" * 50)

    nfc = PN532_I2C(bus=4, debug=False)
    try:
        if not nfc.begin():
            print("[FAIL] PN532 initialization failed.")
            raise SystemExit(1)

        print("\nPlace an NFC card on the PN532 antenna …")
        print("Waiting (timeout = 10 s)", end="", flush=True)

        deadline = time.monotonic() + 10.0
        uid = None
        while time.monotonic() < deadline:
            uid = nfc.read_passive_target_id(timeout=1.0)
            if uid:
                break
            print(".", end="", flush=True)
            time.sleep(0.3)
        print()

        if uid:
            print(f"[OK]  Card detected — UID: {nfc.format_uid(uid)}")
        else:
            print("[FAIL] No card detected within 10 s")

    finally:
        nfc.close()
