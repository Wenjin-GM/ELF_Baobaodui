#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PN532 NFC Module I2C Driver for RK3588 Linux smbus2
==================================================

Applicable to:
    - RK3588 / Linux SBC
    - PN532 I2C mode
    - smbus2
    - I2C address: 0x24
"""

import time
import smbus2


class PN532_I2C:
    """PN532 I2C driver using smbus2 for Linux SBCs."""

    PN532_I2C_ADDRESS = 0x24

    PN532_HOSTTOPN532 = 0xD4
    PN532_PN532TOHOST = 0xD5
    PN532_ACK = [0x00, 0x00, 0xFF, 0x00, 0xFF, 0x00]

    CMD_GETFIRMWAREVERSION = 0x02
    CMD_SAMCONFIGURATION = 0x14
    CMD_INLISTPASSIVETARGET = 0x4A
    CMD_INDATAEXCHANGE = 0x40
    CMD_RFCONFIGURATION = 0x32

    MIFARE_CMD_AUTH_A = 0x60
    MIFARE_CMD_AUTH_B = 0x61
    MIFARE_CMD_READ = 0x30
    MIFARE_CMD_WRITE = 0xA0

    CARD_TYPE_MIFARE_CLASSIC_1K = 0x00

    def __init__(self, bus=4, address=PN532_I2C_ADDRESS, debug=False):
        self.bus_num = bus
        self.address = address
        self.debug = debug
        self.bus = smbus2.SMBus(bus)

    def _log(self, msg):
        if self.debug:
            print(msg)

    def _wakeup(self):
        self._log("[I2C] Wake up PN532...")
        try:
            msg = smbus2.i2c_msg.write(self.address, [0x00] * 16)
            self.bus.i2c_rdwr(msg)
            time.sleep(0.05)
        except OSError:
            time.sleep(0.05)

    def _write_data(self, data):
        payload = list(data)
        self._log("[I2C TX] " + " ".join(f"{b:02X}" for b in payload))
        msg = smbus2.i2c_msg.write(self.address, payload)
        self.bus.i2c_rdwr(msg)

    def _read_raw(self, count):
        msg = smbus2.i2c_msg.read(self.address, count)
        self.bus.i2c_rdwr(msg)
        data = list(msg)
        self._log("[I2C RX RAW] " + " ".join(f"{b:02X}" for b in data))
        return data

    def _read_status(self):
        try:
            data = self._read_raw(1)
            if not data:
                return 0xFF
            return data[0]
        except OSError:
            return 0xFF

    def _wait_ready(self, timeout=1.0):
        start = time.time()
        while time.time() - start < timeout:
            status = self._read_status()
            if status == 0x01:
                return True
            time.sleep(0.005)
        return False

    def _read_data_without_status(self, count):
        raw = self._read_raw(count + 1)
        if not raw:
            return []

        status = raw[0]
        data = raw[1:]
        if status != 0x01:
            self._log(f"[WARN] PN532 status is not ready: 0x{status:02X}")

        self._log("[I2C RX DATA] " + " ".join(f"{b:02X}" for b in data))
        return data

    @staticmethod
    def _build_frame(data):
        length = len(data)
        lcs = (0x100 - length) & 0xFF
        dcs = (0x100 - (sum(data) & 0xFF)) & 0xFF
        return [0x00, 0x00, 0xFF, length, lcs] + list(data) + [dcs, 0x00]

    @staticmethod
    def _find_frame_start(data):
        for i in range(0, len(data) - 2):
            if data[i] == 0x00 and data[i + 1] == 0x00 and data[i + 2] == 0xFF:
                return i
        return -1

    def _read_ack(self):
        ack = self._read_data_without_status(6)
        if ack == self.PN532_ACK:
            self._log("[INFO] ACK received")
            return True

        self._log("[WARN] Invalid ACK: " + " ".join(f"{b:02X}" for b in ack))
        self._log("[WARN] Expected : " + " ".join(f"{b:02X}" for b in self.PN532_ACK))
        return False

    def _read_response_frame(self, max_len=64):
        raw = self._read_raw(max_len + 1)
        if not raw:
            self._log("[WARN] Empty response")
            return None

        status = raw[0]
        data = raw[1:]
        if status != 0x01:
            self._log(f"[WARN] PN532 not ready, status=0x{status:02X}")
            return None

        start = self._find_frame_start(data)
        if start < 0:
            self._log("[WARN] Frame start 00 00 FF not found")
            self._log("[WARN] Data: " + " ".join(f"{b:02X}" for b in data))
            return None

        if len(data) < start + 7:
            self._log("[WARN] Response too short")
            return None

        length = data[start + 3]
        lcs = data[start + 4]

        if length == 0x00:
            possible_ack = data[start:start + 6]
            if possible_ack == self.PN532_ACK:
                self._log("[WARN] Got ACK where response frame expected")
            return None

        if ((length + lcs) & 0xFF) != 0x00:
            self._log("[WARN] Length checksum error")
            return None

        frame_total_len = length + 7
        end = start + frame_total_len
        if len(data) < end:
            self._log("[WARN] Full frame not received")
            self._log(f"[WARN] Need {frame_total_len} bytes, got {len(data) - start} bytes")
            return None

        frame = data[start:end]
        frame_data = frame[5:5 + length]
        dcs = frame[5 + length]
        postamble = frame[6 + length]

        if ((sum(frame_data) + dcs) & 0xFF) != 0x00:
            self._log("[WARN] Data checksum error")
            self._log("[WARN] Frame data: " + " ".join(f"{b:02X}" for b in frame_data))
            self._log(f"[WARN] DCS: 0x{dcs:02X}")
            return None

        if postamble != 0x00:
            self._log(f"[WARN] Unexpected postamble: 0x{postamble:02X}")

        self._log("[PN532 FRAME DATA] " + " ".join(f"{b:02X}" for b in frame_data))
        return frame_data

    def send_command(self, command, params=None, timeout=1.0):
        if params is None:
            params = []

        data = [self.PN532_HOSTTOPN532, command] + list(params)
        frame = self._build_frame(data)

        try:
            self._write_data(frame)
        except OSError as e:
            self._log(f"[ERROR] I2C write failed: {e}")
            return None

        if not self._wait_ready(timeout):
            self._log(f"[WARN] Timeout waiting ACK for cmd 0x{command:02X}")
            return None

        if not self._read_ack():
            return None

        if not self._wait_ready(timeout):
            self._log(f"[WARN] Timeout waiting response for cmd 0x{command:02X}")
            return None

        frame_data = self._read_response_frame(max_len=64)
        if frame_data is None:
            return None

        if len(frame_data) < 2:
            self._log("[WARN] Response frame data too short")
            return None

        tfi = frame_data[0]
        resp_cmd = frame_data[1]
        payload = frame_data[2:]

        if tfi != self.PN532_PN532TOHOST:
            self._log(f"[WARN] Unexpected TFI: 0x{tfi:02X}, expected 0xD5")
            return None

        expected_resp_cmd = (command + 1) & 0xFF
        if resp_cmd != expected_resp_cmd:
            self._log(
                f"[WARN] Unexpected response cmd: 0x{resp_cmd:02X}, "
                f"expected 0x{expected_resp_cmd:02X}"
            )
            return None

        return payload

    def begin(self):
        self._wakeup()
        fw = self.get_firmware_version()

        if fw is None:
            self._log("[WARN] First firmware read failed, retrying...")
            self._wakeup()
            time.sleep(0.1)
            fw = self.get_firmware_version()

        if fw is None:
            print("[ERROR] Cannot communicate with PN532! Check wiring and I2C address.")
            return False

        print(
            f"[INFO] PN532 detected: IC=0x{fw['ic']:02X}, "
            f"Firmware v{fw['ver']}.{fw['rev']}, "
            f"Support=0x{fw['support']:02X}"
        )

        if not self.sam_configuration():
            print("[ERROR] SAM configuration failed!")
            return False

        print("[INFO] PN532 initialized successfully.")
        return True

    def get_firmware_version(self):
        resp = self.send_command(self.CMD_GETFIRMWAREVERSION, timeout=1.0)
        if resp is not None and len(resp) >= 4:
            return {
                "ic": resp[0],
                "ver": resp[1],
                "rev": resp[2],
                "support": resp[3],
            }
        return None

    def sam_configuration(self, mode=0x01, timeout=0x14, irq=False):
        params = [mode, timeout]
        if irq:
            params.append(0x01)
        resp = self.send_command(self.CMD_SAMCONFIGURATION, params, timeout=1.0)
        return resp is not None

    def set_rf_retries(self, max_retries=0x01):
        params = [0x05, 0x01, 0x01, max_retries]
        resp = self.send_command(self.CMD_RFCONFIGURATION, params, timeout=1.0)
        return resp is not None

    def read_passive_target_id(self, card_baud=CARD_TYPE_MIFARE_CLASSIC_1K, timeout=2.0):
        resp = self.send_command(
            self.CMD_INLISTPASSIVETARGET,
            [0x01, card_baud],
            timeout=timeout,
        )

        if resp is None:
            return None

        if len(resp) < 6:
            return None

        nb_targets = resp[0]
        if nb_targets == 0:
            return None

        uid_len = resp[5]
        if len(resp) < 6 + uid_len:
            return None

        uid = resp[6:6 + uid_len]
        return uid

    def mifare_authenticate_block(self, uid, block_number, key, key_type="A"):
        if uid is None:
            return False

        if len(key) != 6:
            print("[ERROR] Mifare key must be 6 bytes")
            return False

        if key_type.upper() == "A":
            auth_cmd = self.MIFARE_CMD_AUTH_A
        else:
            auth_cmd = self.MIFARE_CMD_AUTH_B

        params = [0x01, auth_cmd, block_number]
        params.extend(list(key))
        params.extend(list(uid[:4]))

        resp = self.send_command(self.CMD_INDATAEXCHANGE, params, timeout=1.0)
        if resp is not None and len(resp) > 0 and resp[0] == 0x00:
            return True
        return False

    def mifare_read_block(self, block_number):
        params = [0x01, self.MIFARE_CMD_READ, block_number]
        resp = self.send_command(self.CMD_INDATAEXCHANGE, params, timeout=1.0)
        if resp is not None and len(resp) >= 17 and resp[0] == 0x00:
            return bytes(resp[1:17])
        return None

    def mifare_write_block(self, block_number, data):
        if len(data) != 16:
            print("[ERROR] Data must be exactly 16 bytes")
            return False

        params = [0x01, self.MIFARE_CMD_WRITE, block_number]
        params.extend(list(data))

        resp = self.send_command(self.CMD_INDATAEXCHANGE, params, timeout=1.0)
        if resp is not None and len(resp) > 0 and resp[0] == 0x00:
            return True
        return False

    @staticmethod
    def format_uid(uid):
        if uid is None:
            return "None"
        return " ".join(f"{b:02X}" for b in uid)

    def close(self):
        try:
            self.bus.close()
        except Exception:
            pass


if __name__ == "__main__":
    print("PN532 I2C Driver Self-Test")
    print("=" * 50)
    nfc = PN532_I2C(bus=4, debug=False)
    try:
        if not nfc.begin():
            print("[FAIL] Failed to initialize PN532")
            raise SystemExit(1)

        print("\nPlease place NFC card on PN532 antenna...")
        print("Waiting for card, timeout = 10 seconds")

        start = time.time()
        uid = None
        while time.time() - start < 10:
            uid = nfc.read_passive_target_id(timeout=1.0)
            if uid:
                break
            time.sleep(0.3)

        if uid:
            print("[OK] Card detected!")
            print(f"[OK] UID: {nfc.format_uid(uid)}")
        else:
            print("[FAIL] No card detected within 10 seconds")
    finally:
        nfc.close()
