#!/usr/bin/env python3
"""Validate cabinet inventory zone configuration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from inventory_core import DEFAULT_EXPECTED_COUNTS, load_zones, normalize_class_name


def parse_args():
    parser = argparse.ArgumentParser(description="Check cabinet inventory zones.json.")
    parser.add_argument("--zones", default="vision/inventory/zones.json", help="Zone config JSON.")
    parser.add_argument(
        "--expected-counts",
        default="",
        help='Optional JSON object, e.g. {"vise":2,"insulating gloves":2,"thermometer":2,"multimeter":2}',
    )
    return parser.parse_args()


def main():
    args = parse_args()
    zones_path = Path(args.zones).expanduser()
    zones_data = load_zones(zones_path)
    expected_counts = (
        {normalize_class_name(k): int(v) for k, v in json.loads(args.expected_counts).items()}
        if args.expected_counts
        else dict(DEFAULT_EXPECTED_COUNTS)
    )

    counts = {name: 0 for name in expected_counts}
    problems = []
    seen_ids = set()
    for zone in zones_data["zones"]:
        zone_id = int(zone["zone_id"])
        if zone_id in seen_ids:
            problems.append(f"duplicate zone_id={zone_id}")
        seen_ids.add(zone_id)
        polygon = zone.get("polygon", [])
        if len(polygon) < 3:
            problems.append(f"zone {zone_id} has invalid polygon")
        expected = [normalize_class_name(item) for item in zone.get("expected_classes", [])]
        if not expected:
            problems.append(f"zone {zone_id} has no expected_classes")
        for name in expected:
            if name not in counts:
                problems.append(f"zone {zone_id} uses unexpected class: {name}")
            else:
                counts[name] += 1

    for name, expected in expected_counts.items():
        actual = counts.get(name, 0)
        if actual != expected:
            problems.append(f"class {name}: expected {expected} zones, got {actual}")

    print("===INVENTORY_CONFIG_CHECK===")
    print(json.dumps({
        "zones_path": str(zones_path),
        "zone_count": len(zones_data["zones"]),
        "expected_counts": expected_counts,
        "configured_counts": counts,
        "ok": not problems,
        "problems": problems,
    }, ensure_ascii=False, indent=2))
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
