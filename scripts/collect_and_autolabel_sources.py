"""Collect source AssaultCube images and auto-label them with the current model.

The output is intended for manual correction in annotation tools:
    images/       copied images with stable prefixed names
    labels/       YOLO txt predictions
    preview/      optional rendered prediction previews
    classes.txt   class list for annotation tools
    metadata.csv  source mapping
    predictions.csv predictions with confidence values
"""

from __future__ import annotations

import argparse
import csv
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path

import cv2
from ultralytics import YOLO

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
CLASS_NAMES = ["enemy", "teammate", "EnemyHead"]
DEFAULT_SOURCES = [
    Path(r"C:\AI\dataset\train"),
    Path(r"C:\AI\dataset\valid"),
    Path(r"C:\AI\dataset\test"),
    Path(r"C:\AI\dataset\live_20260610_1000"),
]


def safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value)


def iter_images(source_root: Path) -> list[Path]:
    images_dir = source_root / "images"
    if not images_dir.exists():
        raise FileNotFoundError(f"images directory not found: {images_dir}")
    return sorted(path for path in images_dir.iterdir() if path.suffix.lower() in IMAGE_EXTS)


def yolo_line(box, image_width: int, image_height: int) -> tuple[str, dict[str, float | int]]:
    cls = int(box.cls[0])
    conf = float(box.conf[0])
    x1, y1, x2, y2 = box.xyxy[0].tolist()
    cx = ((x1 + x2) / 2) / image_width
    cy = ((y1 + y2) / 2) / image_height
    width = (x2 - x1) / image_width
    height = (y2 - y1) / image_height
    cx = max(0.0, min(1.0, cx))
    cy = max(0.0, min(1.0, cy))
    width = max(0.0, min(1.0, width))
    height = max(0.0, min(1.0, height))
    line = f"{cls} {cx:.6f} {cy:.6f} {width:.6f} {height:.6f}"
    return line, {
        "class_id": cls,
        "class_name": CLASS_NAMES[cls] if 0 <= cls < len(CLASS_NAMES) else str(cls),
        "confidence": conf,
        "cx": cx,
        "cy": cy,
        "width": width,
        "height": height,
    }


def write_class_files(out_root: Path) -> None:
    text = "\n".join(CLASS_NAMES) + "\n"
    (out_root / "classes.txt").write_text(text, encoding="utf-8")
    labels_dir = out_root / "labels"
    (labels_dir / "classes.txt").write_text(text, encoding="utf-8")
    (labels_dir / "labels.txt").write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect source images and auto-label with AImify")
    parser.add_argument("--out", default=None)
    parser.add_argument("--weights", default=r"C:\AI\assaultcube.pt")
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--device", default="0")
    parser.add_argument("--preview", type=int, default=120)
    parser.add_argument("--sources", nargs="*", default=[str(path) for path in DEFAULT_SOURCES])
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_root = Path(args.out or rf"C:\AI\dataset\aimify_relabel_{timestamp}")
    if out_root.exists():
        if not args.overwrite:
            raise FileExistsError(f"output already exists: {out_root} (pass --overwrite to replace)")
        shutil.rmtree(out_root)

    images_out = out_root / "images"
    labels_out = out_root / "labels"
    preview_out = out_root / "preview"
    images_out.mkdir(parents=True, exist_ok=True)
    labels_out.mkdir(parents=True, exist_ok=True)
    preview_out.mkdir(parents=True, exist_ok=True)
    write_class_files(out_root)

    sources = [Path(source) for source in args.sources]
    copied: list[Path] = []
    metadata_rows: list[dict[str, str]] = []
    seen_names: Counter[str] = Counter()

    for source in sources:
        source_name = safe_name(source.name)
        source_images = iter_images(source)
        for image in source_images:
            stem = f"{source_name}__{image.stem}"
            seen_names[stem] += 1
            if seen_names[stem] > 1:
                stem = f"{stem}_{seen_names[stem]:03d}"
            target = images_out / f"{stem}{image.suffix.lower()}"
            shutil.copy2(image, target)
            copied.append(target)
            metadata_rows.append(
                {
                    "image": target.name,
                    "source": str(image),
                    "source_dataset": source.name,
                }
            )

    with (out_root / "metadata.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["image", "source", "source_dataset"])
        writer.writeheader()
        writer.writerows(metadata_rows)

    model = YOLO(args.weights)
    cls_counter: Counter[int] = Counter()
    frames_with = 0
    previews = 0
    prediction_rows: list[dict[str, str | int | float]] = []

    for start in range(0, len(copied), args.batch):
        batch = copied[start : start + args.batch]
        results = model.predict(
            [str(path) for path in batch],
            conf=args.conf,
            imgsz=args.imgsz,
            device=args.device,
            classes=[0, 1, 2],
            verbose=False,
        )
        for image_path, result in zip(batch, results):
            image_height, image_width = result.orig_shape
            lines: list[str] = []
            for box in result.boxes:
                line, pred = yolo_line(box, image_width, image_height)
                lines.append(line)
                cls = int(pred["class_id"])
                cls_counter[cls] += 1
                prediction_rows.append(
                    {
                        "image": image_path.name,
                        **pred,
                    }
                )

            (labels_out / f"{image_path.stem}.txt").write_text(
                "\n".join(lines) + ("\n" if lines else ""),
                encoding="utf-8",
            )
            if lines:
                frames_with += 1
                if previews < args.preview:
                    cv2.imwrite(str(preview_out / image_path.name), result.plot())
                    previews += 1

        print(f"processed {min(start + args.batch, len(copied))}/{len(copied)}")

    with (out_root / "predictions.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["image", "class_id", "class_name", "confidence", "cx", "cy", "width", "height"],
        )
        writer.writeheader()
        writer.writerows(prediction_rows)

    yaml_text = "\n".join(
        [
            f"path: {out_root.as_posix()}",
            "train: images",
            "val: images",
            f"nc: {len(CLASS_NAMES)}",
            f"names: {CLASS_NAMES!r}",
            "",
        ]
    )
    (out_root / "data.yaml").write_text(yaml_text, encoding="utf-8")

    print(f"out: {out_root}")
    print(f"images: {len(copied)}")
    print(f"frames with predictions: {frames_with}")
    print(f"labels: {labels_out}")
    print(f"preview: {preview_out} ({previews})")
    for cls in sorted(cls_counter):
        name = CLASS_NAMES[cls] if 0 <= cls < len(CLASS_NAMES) else str(cls)
        print(f"{name} ({cls}): {cls_counter[cls]}")


if __name__ == "__main__":
    main()
