from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict


def find_project_root() -> Path:
    for candidate in (
        Path.cwd(),
        Path(__file__).resolve(),
        Path.home() / "smart_tool_cabinet",
    ):
        for path in [candidate, *candidate.parents]:
            if (path / "authorized_cards.json").exists() or (path / "PN532").exists():
                return path
    return Path.home() / "smart_tool_cabinet"


PROJECT_ROOT = find_project_root()
DATA_DIR = PROJECT_ROOT / "data"


def ensure_project_imports() -> None:
    for path in (
        PROJECT_ROOT,
        PROJECT_ROOT / "PN532",
        PROJECT_ROOT / "USB" / "face_auth",
        Path("/home/elf/.local/lib/python3.10/site-packages"),
        Path.home() / ".local/lib/python3.10/site-packages",
    ):
        text = str(path)
        if path.exists() and text not in sys.path:
            sys.path.insert(0, text)


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def timestamp_name() -> str:
    return f"{time.strftime('%Y%m%d_%H%M%S')}_{time.time_ns() % 1_000_000_000:09d}"


def json_text(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def ensure_data_dirs() -> None:
    for name in (
        "inventory_images",
        "inventory_result",
        "ros_logs",
        "events",
        "auth",
        "environment",
        "battery",
        "actuator",
        "ui",
    ):
        (DATA_DIR / name).mkdir(parents=True, exist_ok=True)


def write_json_record(category: str, data: Dict[str, Any], prefix: str | None = None) -> Path:
    ensure_data_dirs()
    safe_category = category.strip().strip("/\\")
    directory = DATA_DIR / safe_category
    directory.mkdir(parents=True, exist_ok=True)
    stem = prefix or safe_category.replace("/", "_")
    path = directory / f"{timestamp_name()}_{stem}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_authorized_cards(path: Path | None = None) -> Dict[str, Dict[str, Any]]:
    cards_path = path or PROJECT_ROOT / "authorized_cards.json"
    try:
        data = json.loads(cards_path.read_text(encoding="utf-8"))
        return data.get("cards", {})
    except Exception:
        return {}


def role_for_card(card_info: Dict[str, Any]) -> str:
    role = str(card_info.get("role", "")).strip().lower()
    if role in {"admin", "user"}:
        return role
    return "admin" if card_info.get("is_admin") else "user"
