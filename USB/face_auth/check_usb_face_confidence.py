#!/usr/bin/env python3
import json
import sys
from pathlib import Path

import cv2

from face_recognition_core import FaceRecognizer


def main():
    if len(sys.argv) > 1:
        capture_dir = Path(sys.argv[1])
    else:
        roots = sorted(
            Path("/home/elf/smart_tool_cabinet/USB").glob("usb_camera_capture_*"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not roots:
            raise SystemExit("no usb_camera_capture_* directory found")
        capture_dir = roots[0]

    recognizer = FaceRecognizer()
    results = []

    for image_path in sorted(capture_dir.glob("usb_camera_0*.jpg")):
        image = cv2.imread(str(image_path))
        if image is None:
            results.append({"file": image_path.name, "status": "read_failed"})
            continue

        face = recognizer.detect_face(image)
        if face is None:
            results.append({"file": image_path.name, "status": "no_face"})
            continue

        feat = recognizer.extract_feature(face)
        name, confidence = recognizer.recognize(feat)
        results.append(
            {
                "file": image_path.name,
                "status": "ok",
                "name": name,
                "confidence": round(float(confidence), 4),
                "confidence_percent": round(float(confidence) * 100, 2),
                "det_score": round(float(face.det_score), 4),
            }
        )

    print("===FACE_CONFIDENCE_JSON===")
    print(json.dumps({"capture_dir": str(capture_dir), "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
