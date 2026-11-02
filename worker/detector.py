"""YOLOv8n detection helper used by the worker."""

import shutil
from pathlib import Path

from ultralytics import YOLO

# Load the model once, at import time, and reuse it for every call.
# The weights sit in the project root; ultralytics downloads them if missing.
WEIGHTS = Path(__file__).resolve().parent.parent / "yolov8n.pt"
MODEL = YOLO(str(WEIGHTS))


def annotate(image_path, output_path, min_confidence=0.25, classes=None):
    """Detect objects in image_path, save the drawn image, return detections.

    classes: optional list of label names (e.g. ["person"]); only those labels
    are detected, drawn and returned. Returns a list of
    {"label": str, "confidence": float, "box": [x1, y1, x2, y2]}.
    """
    # Turn the label names we want into the model's numeric class ids.
    class_ids = None
    if classes is not None:
        class_ids = [i for i, name in MODEL.names.items() if name in classes]
        if not class_ids:  # none of the requested labels exist in the model
            shutil.copyfile(image_path, output_path)
            return []

    # Run inference: conf filters low-confidence boxes, classes keeps our labels.
    results = MODEL.predict(
        source=str(image_path),
        conf=min_confidence,
        classes=class_ids,
        verbose=False,
    )
    result = results[0]

    # Draw the boxes and labels on a copy of the image and save it.
    result.save(filename=str(output_path))

    # Return the same boxes as plain dicts, ready for JSON.
    detections = []
    for box in result.boxes:
        x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
        detections.append(
            {
                "label": result.names[int(box.cls[0])],
                "confidence": round(float(box.conf[0]), 2),
                "box": [x1, y1, x2, y2],
            }
        )
    return detections
