"""Run YOLOv8n on a single image, print detections, save the annotated copy.

Usage: python annotate.py samples/bus.jpg [output path]

Without an explicit output path the result goes to
annotated/<input-name>_annotated.jpg. That folder is created when missing and
is ignored by git, so results never pile up in the project root.
"""

import sys
from pathlib import Path

from ultralytics import YOLO

OUTPUT_DIR = Path("annotated")


def default_output(image_path: Path) -> Path:
    """annotated/<input-name>_annotated.jpg, keyed by the input file name."""
    return OUTPUT_DIR / f"{image_path.stem}_annotated.jpg"


def main() -> int:
    # Two arguments at most: the image path and an optional output path.
    if len(sys.argv) not in (2, 3):
        print("usage: python annotate.py <image path> [output path]")
        return 1

    image_path = Path(sys.argv[1])
    if not image_path.is_file():
        print(f"error: no such file: {image_path}")
        print("usage: python annotate.py <image path> [output path]")
        return 1

    output_path = Path(sys.argv[2]) if len(sys.argv) == 3 else default_output(image_path)

    # Pretrained weights; downloaded automatically on the first run.
    model = YOLO("yolov8n.pt")
    results = model(str(image_path), verbose=False)

    # One line per detection: label, confidence, integer box corners.
    for result in results:
        for box in result.boxes:
            label = result.names[int(box.cls[0])]
            confidence = float(box.conf[0])
            x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
            print(f"{label} {confidence:.2f} box=({x1}, {y1}, {x2}, {y2})")

    # Save a copy of the image with the boxes and labels drawn on it.
    # parents=True: the first run creates annotated/ if it does not exist yet.
    output_path.parent.mkdir(parents=True, exist_ok=True)
    results[0].save(filename=str(output_path))
    print(f"saved {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
