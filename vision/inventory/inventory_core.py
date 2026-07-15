#!/usr/bin/env python3
"""Shared cabinet inventory helpers.

The cabinet camera is fixed, so inventory is treated as a calibrated 2D
problem: detect tools, assign each detection to a configured image zone, then
compare the detected class with that zone's expected class.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

Point = Tuple[float, float]
BBox = Tuple[float, float, float, float]

DEFAULT_EXPECTED_COUNTS: Dict[str, int] = {
    "vise": 2,
    "insulating gloves": 2,
    "thermometer": 2,
    "multimeter": 2,
}

DEFAULT_EXPECTED_ZONE_MIN_CONFIDENCE: Dict[str, float] = {
    # The vise boxes are dark and partly occluded in the fixed cabinet view.
    # Let low-confidence vise detections recover their own calibrated slots,
    # but keep the higher misplaced threshold below for non-zone detections.
    "vise": 0.035,
    "insulating gloves": 0.08,
    "thermometer": 0.08,
    "multimeter": 0.08,
}

DEFAULT_MISPLACED_MIN_CONFIDENCE: Dict[str, float] = {
    "vise": 0.10,
    "insulating gloves": 0.10,
    "thermometer": 0.10,
    "multimeter": 0.10,
}

CLASS_ALIASES: Dict[str, str] = {
    "pliers": "vise",
    "temperature gun": "thermometer",
    "temperature_gun": "thermometer",
    "insulating glove": "insulating gloves",
    "insulating_glove": "insulating gloves",
}


@dataclass
class Detection:
    cls: int
    class_name: str
    confidence: float
    bbox: BBox
    center: Point
    zone_id: Optional[int] = None
    zone_name: str = ""
    placement: str = "unassigned"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cls": self.cls,
            "class_name": self.class_name,
            "confidence": round(float(self.confidence), 4),
            "bbox": [round(float(v), 2) for v in self.bbox],
            "center": [round(float(v), 2) for v in self.center],
            "zone_id": self.zone_id,
            "zone_name": self.zone_name,
            "placement": self.placement,
        }


def normalize_class_name(name: str) -> str:
    text = re.sub(r"\s+", " ", str(name).strip().lower().replace("_", " "))
    return CLASS_ALIASES.get(text, text)


def safe_name(name: str) -> str:
    text = normalize_class_name(name)
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "tool"


def center_of_bbox(bbox: Sequence[float]) -> Point:
    x1, y1, x2, y2 = [float(v) for v in bbox]
    return ((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def expand_bbox_to_polygon(bbox: Sequence[float], image_size: Sequence[int], ratio: float) -> List[List[int]]:
    x1, y1, x2, y2 = [float(v) for v in bbox]
    width, height = int(image_size[0]), int(image_size[1])
    bw = max(1.0, x2 - x1)
    bh = max(1.0, y2 - y1)
    pad_x = bw * ratio
    pad_y = bh * ratio
    left = max(0, int(round(x1 - pad_x)))
    top = max(0, int(round(y1 - pad_y)))
    right = min(width - 1, int(round(x2 + pad_x)))
    bottom = min(height - 1, int(round(y2 + pad_y)))
    return [[left, top], [right, top], [right, bottom], [left, bottom]]


def polygon_bounds(polygon: Sequence[Sequence[float]]) -> BBox:
    xs = [float(p[0]) for p in polygon]
    ys = [float(p[1]) for p in polygon]
    return (min(xs), min(ys), max(xs), max(ys))


def point_in_polygon(point: Point, polygon: Sequence[Sequence[float]]) -> bool:
    x, y = point
    inside = False
    points = [(float(px), float(py)) for px, py in polygon]
    if len(points) < 3:
        return False
    j = len(points) - 1
    for i, (xi, yi) in enumerate(points):
        xj, yj = points[j]
        crosses = (yi > y) != (yj > y)
        if crosses:
            slope_x = (xj - xi) * (y - yi) / ((yj - yi) or 1e-9) + xi
            if x < slope_x:
                inside = not inside
        j = i
    return inside


def bbox_center_distance(bbox: BBox, point: Point) -> float:
    cx, cy = center_of_bbox(bbox)
    return math.hypot(cx - point[0], cy - point[1])


def load_zones(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    zones = data.get("zones", [])
    if not isinstance(zones, list) or not zones:
        raise ValueError(f"zones file has no zones: {path}")
    for zone in zones:
        if "zone_id" not in zone or "polygon" not in zone:
            raise ValueError(f"invalid zone entry: {zone}")
        zone["expected_classes"] = [
            normalize_class_name(item) for item in zone.get("expected_classes", [])
        ]
    return data


def write_zones(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def build_zones_from_detections(
    detections: Sequence[Detection],
    image_size: Sequence[int],
    expected_counts: Optional[Dict[str, int]] = None,
    expand_ratio: float = 0.35,
) -> Dict[str, Any]:
    expected = {
        normalize_class_name(name): int(count)
        for name, count in (expected_counts or DEFAULT_EXPECTED_COUNTS).items()
    }
    by_class: Dict[str, List[Detection]] = {name: [] for name in expected}
    for det in detections:
        name = normalize_class_name(det.class_name)
        if name in by_class:
            by_class[name].append(det)

    errors = []
    for name, count in expected.items():
        if len(by_class[name]) < count:
            errors.append(f"{name}: expected at least {count}, detected {len(by_class[name])}")
    if errors:
        raise ValueError("cannot calibrate zones from current image: " + "; ".join(errors))

    ordered: List[Detection] = []
    for name in sorted(expected.keys()):
        top_detections = sorted(by_class[name], key=lambda d: d.confidence, reverse=True)[: expected[name]]
        ordered.extend(sorted(top_detections, key=lambda d: (d.center[1], d.center[0])))
    ordered.sort(key=lambda d: (d.center[1], d.center[0], normalize_class_name(d.class_name)))

    zones = []
    class_index: Dict[str, int] = {}
    for zone_id, det in enumerate(ordered, start=1):
        class_name = normalize_class_name(det.class_name)
        class_index[class_name] = class_index.get(class_name, 0) + 1
        zone_name = f"{safe_name(class_name)}_{class_index[class_name]}_zone"
        polygon = expand_bbox_to_polygon(det.bbox, image_size, expand_ratio)
        zones.append(
            {
                "zone_id": zone_id,
                "zone_name": zone_name,
                "expected_classes": [class_name],
                "polygon": polygon,
                "calibrated_bbox": [round(float(v), 2) for v in det.bbox],
                "calibrated_center": [round(float(v), 2) for v in det.center],
            }
        )

    return {
        "version": 1,
        "image_size": [int(image_size[0]), int(image_size[1])],
        "assignment_point": "bbox_center",
        "ignore_unassigned_detections": True,
        "expected_counts": expected,
        "zones": zones,
    }


def assign_detections_to_zones(detections: Sequence[Detection], zones_data: Dict[str, Any]) -> None:
    zones = zones_data.get("zones", [])
    for det in detections:
        containing = [zone for zone in zones if point_in_polygon(det.center, zone.get("polygon", []))]
        if containing:
            class_name = normalize_class_name(det.class_name)
            preferred = [
                zone for zone in containing
                if class_name in [normalize_class_name(item) for item in zone.get("expected_classes", [])]
            ]
            if preferred:
                containing = preferred
            containing.sort(key=lambda z: bbox_center_distance(polygon_bounds(z["polygon"]), det.center))
            zone = containing[0]
            det.zone_id = int(zone["zone_id"])
            det.zone_name = str(zone.get("zone_name", f"zone_{det.zone_id}"))
        else:
            det.zone_id = None
            det.zone_name = ""


def _confidence_map(raw: Any, defaults: Dict[str, float]) -> Dict[str, float]:
    values = dict(defaults)
    if isinstance(raw, dict):
        for key, value in raw.items():
            try:
                values[normalize_class_name(key)] = float(value)
            except (TypeError, ValueError):
                continue
    return values


def _zone_expected_by_id(zones_data: Dict[str, Any]) -> Dict[int, List[str]]:
    expected_by_id: Dict[int, List[str]] = {}
    for zone in zones_data.get("zones", []):
        try:
            zone_id = int(zone["zone_id"])
        except (KeyError, TypeError, ValueError):
            continue
        expected_by_id[zone_id] = [
            normalize_class_name(item) for item in zone.get("expected_classes", [])
        ]
    return expected_by_id


def filter_inventory_detections(
    detections: Sequence[Detection],
    zones_data: Dict[str, Any],
) -> Tuple[List[Detection], List[Detection]]:
    """Keep low confidence boxes only when they recover their own zone.

    The cabinet view is fixed, so a weak detection inside the calibrated slot
    for the same class is useful evidence. Weak boxes outside their own slots
    are much more likely to be clutter or overlapping YOLO false positives, so
    they are ignored before placement status is calculated.
    """
    expected_min = _confidence_map(
        zones_data.get("expected_zone_min_confidence"),
        DEFAULT_EXPECTED_ZONE_MIN_CONFIDENCE,
    )
    misplaced_min = _confidence_map(
        zones_data.get("misplaced_min_confidence"),
        DEFAULT_MISPLACED_MIN_CONFIDENCE,
    )
    default_expected_min = float(zones_data.get("default_expected_zone_min_confidence", 0.08))
    default_misplaced_min = float(zones_data.get("default_misplaced_min_confidence", 0.10))
    expected_by_id = _zone_expected_by_id(zones_data)

    kept: List[Detection] = []
    ignored: List[Detection] = []
    for det in detections:
        class_name = normalize_class_name(det.class_name)
        same_expected_zone = (
            det.zone_id is not None
            and class_name in expected_by_id.get(int(det.zone_id), [])
        )
        threshold = (
            expected_min.get(class_name, default_expected_min)
            if same_expected_zone
            else misplaced_min.get(class_name, default_misplaced_min)
        )
        if float(det.confidence) >= threshold:
            kept.append(det)
        else:
            det.placement = "ignored_low_confidence"
            ignored.append(det)
    return kept, ignored


def analyze_inventory(detections: Sequence[Detection], zones_data: Dict[str, Any]) -> Dict[str, Any]:
    assign_detections_to_zones(detections, zones_data)
    active_detections, ignored_low_confidence = filter_inventory_detections(detections, zones_data)
    zones_result = []
    all_normal = True
    detections_by_zone: Dict[int, List[Detection]] = {}
    unassigned: List[Detection] = []
    ignore_unassigned = bool(zones_data.get("ignore_unassigned_detections", True))
    for det in active_detections:
        if det.zone_id is None:
            det.placement = "unassigned"
            unassigned.append(det)
            if not ignore_unassigned:
                all_normal = False
        else:
            detections_by_zone.setdefault(det.zone_id, []).append(det)

    for zone in zones_data.get("zones", []):
        zone_id = int(zone["zone_id"])
        expected = [normalize_class_name(item) for item in zone.get("expected_classes", [])]
        zone_dets = detections_by_zone.get(zone_id, [])
        matching_all = [det for det in zone_dets if normalize_class_name(det.class_name) in expected]
        matching = sorted(matching_all, key=lambda d: d.confidence, reverse=True)[: len(expected)]
        duplicate_matching = sorted(matching_all, key=lambda d: d.confidence, reverse=True)[len(expected):]
        wrong = [det for det in zone_dets if normalize_class_name(det.class_name) not in expected]
        missing_count = max(0, len(expected) - len(matching))
        extra_count = len(duplicate_matching) + len(wrong)

        # The fixed cabinet view can produce overlapping false-positive boxes.
        # If the expected class is present in the zone, treat conflicting boxes
        # in that same zone as ignored conflicts instead of a placement fault.
        if matching and (wrong or duplicate_matching):
            status = "normal"
        elif wrong:
            status = "misplaced"
        elif missing_count:
            status = "missing"
        elif extra_count:
            status = "extra"
        else:
            status = "normal"

        if status != "normal":
            all_normal = False

        for det in matching:
            det.placement = "normal"
        for det in duplicate_matching:
            det.placement = "ignored_duplicate"
        for det in wrong:
            det.placement = "ignored_conflict" if matching else "misplaced"

        zones_result.append(
            {
                "zone_id": zone_id,
                "zone_name": str(zone.get("zone_name", f"zone_{zone_id}")),
                "expected_classes": expected,
                "registered": len(expected),
                "current": len(matching),
                "borrowed": missing_count,
                "extra": extra_count,
                "status": status,
                "detected_classes": [det.class_name for det in zone_dets],
                "ignored_conflicts": [det.to_dict() for det in wrong] if matching else [],
                "ignored_duplicates": [det.to_dict() for det in duplicate_matching],
                "detections": [det.to_dict() for det in zone_dets],
            }
        )

    message = "inventory normal"
    if not all_normal:
        abnormal = [z for z in zones_result if z["status"] != "normal"]
        parts = [f"{z['zone_name']}={z['status']}" for z in abnormal]
        if unassigned:
            parts.append(f"unassigned={len(unassigned)}")
        message = "inventory abnormal: " + ", ".join(parts)

    return {
        "is_normal": all_normal,
        "zones": zones_result,
        "detections": [det.to_dict() for det in active_detections],
        "ignored_detections": [det.to_dict() for det in ignored_low_confidence],
        "unassigned": [det.to_dict() for det in unassigned],
        "message": message,
    }


def expected_counts_from_text(text: str) -> Dict[str, int]:
    if not text:
        return dict(DEFAULT_EXPECTED_COUNTS)
    data = json.loads(text)
    return {normalize_class_name(k): int(v) for k, v in data.items()}


def detections_from_yolo_result(result: Any, names: Any) -> List[Detection]:
    detections: List[Detection] = []
    boxes = getattr(result, "boxes", None)
    if boxes is None:
        return detections
    for box in boxes:
        cls_id = int(box.cls[0].item())
        confidence = float(box.conf[0].item())
        xyxy = box.xyxy[0].tolist()
        class_name = normalize_class_name(names.get(cls_id, str(cls_id)) if isinstance(names, dict) else names[cls_id])
        detections.append(
            Detection(
                cls=cls_id,
                class_name=class_name,
                confidence=confidence,
                bbox=tuple(float(v) for v in xyxy),
                center=center_of_bbox(xyxy),
            )
        )
    detections.sort(key=lambda d: (-d.confidence, d.class_name, d.center[1], d.center[0]))
    return detections


def summarize_counts(detections: Iterable[Detection]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for det in detections:
        name = normalize_class_name(det.class_name)
        counts[name] = counts.get(name, 0) + 1
    return counts
