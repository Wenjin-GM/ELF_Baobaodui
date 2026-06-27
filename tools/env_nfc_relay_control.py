#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SHT30 + PN532 + active-low relay integration for ELF 2 / RK3588.

Default wiring used by this script, see ../docs/connect_way.md:
    SHT30  -> I2C4, address 0x44
    PN532  -> I2C7, address 0x24
    GPIO.25 -> relay 3 -> electromagnetic lock, active low
    GPIO.28 -> relay 2 -> fan, active low

Run from /home/elf/smart_tool_cabinet:
    sudo python3 tools/env_nfc_relay_control.py enroll --name my_card
    sudo python3 tools/env_nfc_relay_control.py run
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional, Set, Tuple

import gpiod
import smbus2


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from PN532.drivers.i2c_pn532 import PN532_I2C
except ImportError as exc:
    raise SystemExit(
        "Cannot import PN532 driver. Keep the workspace layout intact and run from "
        "/home/elf/smart_tool_cabinet or use tools/env_nfc_relay_control.py."
    ) from exc


CARD_DB_DEFAULT = PROJECT_ROOT / "authorized_cards.json"
FACE_ROOT_DEFAULT = PROJECT_ROOT / "USB/face_auth"
FACE_DB_DEFAULT = FACE_ROOT_DEFAULT / "face_db"
FACE_CAMERA_DEFAULT = "/dev/video21"

SHT30_DEFAULT_BUS = 4
SHT30_DEFAULT_ADDR = 0x44
PN532_DEFAULT_BUS = 7
PN532_DEFAULT_ADDR = 0x24

# Latest relay defaults from docs/connect_way.md:
#   GPIO.25 -> GPIO2_C1--GPIO3_A3 -> gpiochip3 line 3, relay 3, lock
#   GPIO.28 -> GPIO2_D3--GPIO3_B1 -> gpiochip3 line 9, relay 2, fan
DEFAULT_RELAY_CHIP = "gpiochip3"
DEFAULT_LOCK_LINE = 3
DEFAULT_FAN_LINE = 9

RELAY_ACTIVE = 0
RELAY_INACTIVE = 1
DEFAULT_FACE_NAMES = "赵增辉,高硕"


def add_user_site_packages() -> None:
    for path in (
        Path("/home/elf/.local/lib/python3.10/site-packages"),
        Path.home() / ".local/lib/python3.10/site-packages",
    ):
        path_text = str(path)
        if path.exists() and path_text not in sys.path:
            sys.path.insert(0, path_text)


add_user_site_packages()


def format_uid(uid: Iterable[int]) -> str:
    return "".join(f"{byte:02X}" for byte in uid)


def now_text() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def parse_name_set(value: str) -> Set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


class SHT30Sensor:
    def __init__(self, bus: int = SHT30_DEFAULT_BUS, address: int = SHT30_DEFAULT_ADDR):
        self.bus_num = bus
        self.address = address
        self.bus = smbus2.SMBus(bus)

    @staticmethod
    def _crc8(data: Iterable[int]) -> int:
        crc = 0xFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x80:
                    crc = ((crc << 1) ^ 0x31) & 0xFF
                else:
                    crc = (crc << 1) & 0xFF
        return crc

    def read(self) -> Tuple[float, float]:
        self.bus.write_i2c_block_data(self.address, 0x2C, [0x06])
        time.sleep(0.02)
        data = self.bus.read_i2c_block_data(self.address, 0x00, 6)

        if self._crc8(data[0:2]) != data[2]:
            raise RuntimeError("SHT30 temperature CRC check failed")
        if self._crc8(data[3:5]) != data[5]:
            raise RuntimeError("SHT30 humidity CRC check failed")

        temp_raw = (data[0] << 8) | data[1]
        humid_raw = (data[3] << 8) | data[4]
        temperature = -45.0 + 175.0 * temp_raw / 65535.0
        humidity = 100.0 * humid_raw / 65535.0
        return temperature, humidity

    def close(self) -> None:
        self.bus.close()


class ActiveLowRelay:
    def __init__(self, chip_name: str, line_offset: int, name: str):
        self.chip_name = chip_name
        self.line_offset = line_offset
        self.name = name
        self.chip = gpiod.Chip(chip_name)
        self.line = self.chip.get_line(line_offset)

        try:
            self.line.request(
                consumer=f"elf2_{name}_relay",
                type=gpiod.LINE_REQ_DIR_OUT,
                default_vals=[RELAY_INACTIVE],
            )
        except TypeError:
            self.line.request(consumer=f"elf2_{name}_relay", type=gpiod.LINE_REQ_DIR_OUT)
            self.off()

    def on(self) -> None:
        self.line.set_value(RELAY_ACTIVE)

    def off(self) -> None:
        self.line.set_value(RELAY_INACTIVE)

    def pulse(self, seconds: float) -> None:
        self.on()
        time.sleep(seconds)
        self.off()

    def close(self) -> None:
        try:
            self.off()
        finally:
            self.line.release()
            self.chip.close()


class FaceAuthCamera:
    def __init__(
        self,
        camera: str,
        face_root: Path,
        face_db: Path,
        allowed_names: Set[str],
        min_confidence: float,
        width: int = 640,
        height: int = 480,
    ):
        self.camera = camera
        self.face_root = face_root
        self.face_db = face_db
        self.allowed_names = allowed_names
        self.min_confidence = min_confidence
        self.width = width
        self.height = height
        self.cv2 = None
        self.cap = None
        self.recognizer = None

    def open(self) -> None:
        import cv2

        self.cv2 = cv2
        core_path = self.face_root / "face_recognition_core.py"
        if not core_path.exists():
            raise RuntimeError(f"Face core not found: {core_path}")
        if not self.face_db.exists():
            raise RuntimeError(f"Face DB not found: {self.face_db}")

        spec = importlib.util.spec_from_file_location("elf2_face_recognition_core", core_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Cannot load face core: {core_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        self.recognizer = module.FaceRecognizer(face_db_dir=str(self.face_db))

        camera_source = int(self.camera) if self.camera.isdigit() else self.camera
        self.cap = cv2.VideoCapture(camera_source, cv2.CAP_V4L2)
        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open USB camera: {self.camera}")
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

    def recognize_once(self) -> Tuple[Optional[str], float, str]:
        if self.cap is None or self.recognizer is None:
            raise RuntimeError("FaceAuthCamera is not opened")

        ok, frame = self.cap.read()
        if not ok or frame is None:
            return None, 0.0, "no_frame"

        face = self.recognizer.detect_face(frame)
        if face is None:
            return None, 0.0, "no_face"

        feat = self.recognizer.extract_feature(face)
        name, confidence = self.recognizer.recognize(feat)
        if name in self.allowed_names and confidence >= self.min_confidence:
            return name, confidence, "allowed"
        return name, confidence, "denied"

    def close(self) -> None:
        if self.cap is not None:
            self.cap.release()
            self.cap = None


class CardStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> Dict[str, Dict[str, str]]:
        if not self.path.exists():
            return {}
        with self.path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("cards", {})

    def save_card(self, uid: str, name: str) -> None:
        cards = self.load()
        cards[uid] = {"name": name, "enrolled_at": now_text()}
        payload = {"cards": cards}
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")


def open_nfc(bus: int, address: int, debug: bool) -> PN532_I2C:
    nfc = PN532_I2C(bus=bus, address=address, debug=debug)
    if not nfc.begin():
        raise RuntimeError(f"PN532 init failed on /dev/i2c-{bus} address 0x{address:02X}")
    return nfc


def wait_for_card(nfc: PN532_I2C, timeout: float, message: str) -> Optional[str]:
    print(message)
    start = time.time()
    while time.time() - start < timeout:
        uid = nfc.read_passive_target_id(timeout=1.0)
        if uid:
            return format_uid(uid)
        time.sleep(0.2)
    return None


def cmd_enroll(args: argparse.Namespace) -> int:
    nfc = open_nfc(args.nfc_bus, args.nfc_addr, args.debug)
    uid = wait_for_card(nfc, args.timeout, "Place the card on PN532 to enroll...")
    if not uid:
        print("No card detected.")
        return 1

    store = CardStore(args.card_db)
    store.save_card(uid, args.name or uid)
    print(f"Enrolled card UID={uid}, name={args.name or uid}, db={args.card_db}")
    return 0


def cmd_read_card(args: argparse.Namespace) -> int:
    nfc = open_nfc(args.nfc_bus, args.nfc_addr, args.debug)
    uid = wait_for_card(nfc, args.timeout, "Place the card on PN532 to read UID...")
    if not uid:
        print("No card detected.")
        return 1
    print(f"UID={uid}")
    return 0


def cmd_read_sht30(args: argparse.Namespace) -> int:
    sensor = SHT30Sensor(args.sht_bus, args.sht_addr)
    try:
        temperature, humidity = sensor.read()
        print(f"Temperature={temperature:.2f} C, Humidity={humidity:.2f}%RH")
    finally:
        sensor.close()
    return 0


def cmd_test_relay(args: argparse.Namespace) -> int:
    line = args.lock_line if args.target == "lock" else args.fan_line
    relay = ActiveLowRelay(args.relay_chip, line, args.target)
    try:
        print(
            f"Testing {args.target}: {args.relay_chip} line {line}, "
            f"LOW for {args.seconds:.2f}s"
        )
        relay.pulse(args.seconds)
        print("Relay returned to HIGH/inactive.")
    finally:
        relay.close()
    return 0


def cmd_test_face(args: argparse.Namespace) -> int:
    allowed_names = parse_name_set(args.face_names)
    face = FaceAuthCamera(
        camera=args.face_camera,
        face_root=args.face_root,
        face_db=args.face_db,
        allowed_names=allowed_names,
        min_confidence=args.face_confidence,
        width=args.face_width,
        height=args.face_height,
    )
    try:
        print(
            f"Opening face auth camera={args.face_camera}, "
            f"allowed={','.join(sorted(allowed_names))}"
        )
        face.open()
        start = time.time()
        while time.time() - start < args.timeout:
            name, confidence, status = face.recognize_once()
            if status == "allowed":
                print(f"[FACE AUTH] {name} confidence={confidence:.4f}")
                return 0
            if status == "denied":
                print(f"[FACE DENY] {name} confidence={confidence:.4f}")
            elif status == "no_face":
                print("[FACE] no face")
            else:
                print(f"[FACE] {status}")
            time.sleep(args.face_interval)
        print("No allowed face detected.")
        return 1
    finally:
        face.close()


@dataclass
class RunState:
    fan_on: bool = False
    last_lock_opened: float = 0.0
    last_face_checked: float = 0.0


def cmd_run(args: argparse.Namespace) -> int:
    cards = CardStore(args.card_db).load()
    if not cards:
        print(f"[WARN] No authorized card in {args.card_db}. NFC unlock will deny all cards until enroll.")

    if cards:
        print(f"Loaded {len(cards)} authorized card(s): {', '.join(cards.keys())}")
    sensor = SHT30Sensor(args.sht_bus, args.sht_addr)
    nfc = open_nfc(args.nfc_bus, args.nfc_addr, args.debug)
    lock = ActiveLowRelay(args.relay_chip, args.lock_line, "lock")
    fan = ActiveLowRelay(args.relay_chip, args.fan_line, "fan")
    face = None
    if args.face_enable:
        face = FaceAuthCamera(
            camera=args.face_camera,
            face_root=args.face_root,
            face_db=args.face_db,
            allowed_names=parse_name_set(args.face_names),
            min_confidence=args.face_confidence,
            width=args.face_width,
            height=args.face_height,
        )
        try:
            face.open()
            print(
                f"Face auth enabled: camera={args.face_camera}, "
                f"allowed={args.face_names}, min_confidence={args.face_confidence:.2f}"
            )
        except Exception as exc:
            print(f"[WARN] Face auth disabled: {exc}")
            face = None

    state = RunState()
    stop = {"value": False}

    def handle_stop(_signum, _frame):
        stop["value"] = True

    signal.signal(signal.SIGINT, handle_stop)
    signal.signal(signal.SIGTERM, handle_stop)

    try:
        print("System running. Press Ctrl+C to stop.")
        while not stop["value"]:
            try:
                temperature, humidity = sensor.read()
                print(
                    f"[{now_text()}] temp={temperature:.2f}C "
                    f"humidity={humidity:.2f}%RH fan={'ON' if state.fan_on else 'OFF'}"
                )

                if not state.fan_on and humidity > args.humidity_on:
                    fan.on()
                    state.fan_on = True
                    print(f"[FAN] humidity > {args.humidity_on:.1f}%RH, fan ON")
                elif state.fan_on and humidity <= args.humidity_off:
                    fan.off()
                    state.fan_on = False
                    print(f"[FAN] humidity <= {args.humidity_off:.1f}%RH, fan OFF")
            except Exception as exc:
                print(f"[WARN] SHT30 read/control failed: {exc}")

            try:
                uid = nfc.read_passive_target_id(timeout=args.nfc_timeout)
                if uid:
                    uid_text = format_uid(uid)
                    card = cards.get(uid_text)
                    if card:
                        since_last = time.time() - state.last_lock_opened
                        if since_last >= args.lock_cooldown:
                            print(f"[AUTH] UID={uid_text} allowed ({card.get('name', uid_text)}), opening lock")
                            lock.pulse(args.lock_seconds)
                            state.last_lock_opened = time.time()
                        else:
                            print(f"[AUTH] UID={uid_text} allowed, ignored during cooldown")
                    else:
                        print(f"[DENY] UID={uid_text} is not authorized")
            except Exception as exc:
                print(f"[WARN] PN532 read failed: {exc}")

            if face is not None:
                try:
                    if time.time() - state.last_face_checked >= args.face_interval:
                        state.last_face_checked = time.time()
                        name, confidence, status = face.recognize_once()
                        if status == "allowed":
                            since_last = time.time() - state.last_lock_opened
                            if since_last >= args.lock_cooldown:
                                print(f"[FACE AUTH] {name} confidence={confidence:.4f}, opening lock")
                                lock.pulse(args.lock_seconds)
                                state.last_lock_opened = time.time()
                            else:
                                print(f"[FACE AUTH] {name} allowed, ignored during cooldown")
                        elif status == "denied":
                            print(f"[FACE DENY] {name} confidence={confidence:.4f}")
                except Exception as exc:
                    print(f"[WARN] Face recognition failed: {exc}")

            time.sleep(args.loop_interval)
    finally:
        print("Stopping, setting relays HIGH/inactive.")
        if face is not None:
            face.close()
        fan.close()
        lock.close()
        sensor.close()

    return 0


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--sht-bus", type=int, default=SHT30_DEFAULT_BUS)
    parser.add_argument("--sht-addr", type=lambda x: int(x, 0), default=SHT30_DEFAULT_ADDR)
    parser.add_argument("--nfc-bus", type=int, default=PN532_DEFAULT_BUS)
    parser.add_argument("--nfc-addr", type=lambda x: int(x, 0), default=PN532_DEFAULT_ADDR)
    parser.add_argument("--relay-chip", default=DEFAULT_RELAY_CHIP)
    parser.add_argument("--lock-line", type=int, default=DEFAULT_LOCK_LINE)
    parser.add_argument("--fan-line", type=int, default=DEFAULT_FAN_LINE)
    parser.add_argument("--card-db", type=Path, default=CARD_DB_DEFAULT)
    parser.add_argument("--debug", action="store_true")


def add_face_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--face-camera", default=FACE_CAMERA_DEFAULT)
    parser.add_argument("--face-root", type=Path, default=FACE_ROOT_DEFAULT)
    parser.add_argument("--face-db", type=Path, default=FACE_DB_DEFAULT)
    parser.add_argument("--face-names", default=DEFAULT_FACE_NAMES)
    parser.add_argument("--face-confidence", type=float, default=0.40)
    parser.add_argument("--face-width", type=int, default=640)
    parser.add_argument("--face-height", type=int, default=480)
    parser.add_argument("--face-interval", type=float, default=1.0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ELF 2 SHT30 + PN532 + relay integration")
    subparsers = parser.add_subparsers(dest="command", required=True)

    enroll = subparsers.add_parser("enroll", help="read one card UID and add it to the local allow-list")
    add_common_args(enroll)
    enroll.add_argument("--name", default="")
    enroll.add_argument("--timeout", type=float, default=30.0)
    enroll.set_defaults(func=cmd_enroll)

    read_card = subparsers.add_parser("read-card", help="read and print one card UID without saving")
    add_common_args(read_card)
    read_card.add_argument("--timeout", type=float, default=30.0)
    read_card.set_defaults(func=cmd_read_card)

    read_sht30 = subparsers.add_parser("read-sht30", help="read SHT30 once")
    add_common_args(read_sht30)
    read_sht30.set_defaults(func=cmd_read_sht30)

    test_relay = subparsers.add_parser("test-relay", help="pulse lock or fan relay once")
    add_common_args(test_relay)
    test_relay.add_argument("target", choices=("lock", "fan"))
    test_relay.add_argument("--seconds", type=float, default=0.5)
    test_relay.set_defaults(func=cmd_test_relay)

    test_face = subparsers.add_parser("test-face", help="test USB camera face recognition once")
    add_common_args(test_face)
    add_face_args(test_face)
    test_face.add_argument("--timeout", type=float, default=20.0)
    test_face.set_defaults(func=cmd_test_face)

    run = subparsers.add_parser("run", help="run humidity fan control, NFC lock control, and face unlock")
    add_common_args(run)
    add_face_args(run)
    run.add_argument("--face-enable", action=argparse.BooleanOptionalAction, default=True)
    run.add_argument("--humidity-on", type=float, default=55.0)
    run.add_argument("--humidity-off", type=float, default=50.0)
    run.add_argument("--lock-seconds", type=float, default=0.8)
    run.add_argument("--lock-cooldown", type=float, default=3.0)
    run.add_argument("--nfc-timeout", type=float, default=0.5)
    run.add_argument("--loop-interval", type=float, default=0.5)
    run.set_defaults(func=cmd_run)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if hasattr(args, "humidity_off") and args.humidity_off >= args.humidity_on:
        parser.error("--humidity-off must be lower than --humidity-on")
    if hasattr(args, "seconds") and (args.seconds <= 0 or args.seconds > 5):
        parser.error("--seconds must be > 0 and <= 5")
    if hasattr(args, "lock_seconds") and (args.lock_seconds <= 0 or args.lock_seconds > 5):
        parser.error("--lock-seconds must be > 0 and <= 5")

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
