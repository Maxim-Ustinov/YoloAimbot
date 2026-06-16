"""Collect a live AssaultCube image batch and optionally auto-label it.

Example:
    python -m scripts.collect_live_dataset --name live_20260610_1000 --count 1000 --interval 0.4 --autolabel
    python -m scripts.collect_live_dataset --name live_20260610_1000 --skip-collect --autolabel

Output layout:
    dataset/<name>/images/frame_00000.jpg
    dataset/<name>/labels/frame_00000.txt
    dataset/<name>/labels/classes.txt
    dataset/<name>/autolabel_preview/*.jpg
"""

from __future__ import annotations

import argparse
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import cv2
from ultralytics import YOLO

from src.capture import ScreenCapture
from src.detect.detector import DEFAULT_WEIGHTS, resolve_weights

EXTS = {".jpg", ".jpeg", ".png"}
NAMES = {0: "enemy", 1: "teammate", 2: "EnemyHead"}


def dataset_root(name: str | None) -> Path:
    if not name:
        name = "live_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    return Path("dataset") / name


def next_index(images_dir: Path) -> int:
    existing = sorted(images_dir.glob("frame_*.jpg"))
    if not existing:
        return 0
    return int(existing[-1].stem.split("_")[1]) + 1


def model_class_ids(model: YOLO) -> list[int]:
    names = getattr(model, "names", {})
    try:
        class_count = len(names)
    except TypeError:
        class_count = 2
    return [cls for cls in sorted(NAMES) if cls < class_count]


def class_file_text(model: YOLO, class_ids: list[int]) -> str:
    names = getattr(model, "names", {})
    lines: list[str] = []
    for cls in class_ids:
        if isinstance(names, dict):
            lines.append(str(names.get(cls, NAMES.get(cls, cls))))
        else:
            lines.append(str(NAMES.get(cls, cls)))
    return "\n".join(lines) + "\n"


def collect_images(root: Path, count: int, interval: float, countdown: int, capture_fps: int) -> None:
    images_dir = root / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    start_idx = next_index(images_dir)

    for second in range(countdown, 0, -1):
        print(f"start in {second}... switch to AssaultCube")
        time.sleep(1)

    capture = ScreenCapture(region=None, target_fps=capture_fps)
    capture.start()
    try:
        for i in range(count):
            frame = capture.latest_frame(timeout=2.0)
            if frame is None:
                print(f"skip {i + 1}/{count}: no frame")
                time.sleep(interval)
                continue

            path = images_dir / f"frame_{start_idx + i:05d}.jpg"
            cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            if (i + 1) % 25 == 0 or i + 1 == count:
                print(f"saved {i + 1}/{count} -> {images_dir}")
            time.sleep(interval)
    finally:
        capture.close()


def autolabel(root: Path, weights: str, conf: float, imgsz: int, device: str, batch: int, preview: int) -> None:
    images_dir = root / "images"
    labels_dir = root / "labels"
    preview_dir = root / "autolabel_preview"
    images = sorted(p for p in images_dir.glob("*") if p.suffix.lower() in EXTS)
    if not images:
        print(f"no images found in {images_dir}")
        return

    resolved = resolve_weights(weights)
    model = YOLO(str(resolved))
    class_ids = model_class_ids(model)
    labels_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)
    classes_text = class_file_text(model, class_ids)
    (labels_dir / "classes.txt").write_text(classes_text, encoding="utf-8")
    (labels_dir / "labels.txt").write_text(classes_text, encoding="utf-8")
    cls_counter: Counter[int] = Counter()
    frames_with = 0
    previews_saved = 0

    print(
        f"autolabel: weights={resolved}, conf={conf}, imgsz={imgsz}, "
        f"classes={class_ids}, images={len(images)}"
    )
    for start in range(0, len(images), batch):
        chunk = images[start : start + batch]
        results = model.predict(
            [str(path) for path in chunk],
            conf=conf,
            imgsz=imgsz,
            device=device,
            classes=class_ids,
            verbose=False,
        )

        for img_path, res in zip(chunk, results):
            h, w = res.orig_shape
            lines: list[str] = []
            for box in res.boxes:
                cls = int(box.cls[0])
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                cx = (x1 + x2) / 2 / w
                cy = (y1 + y2) / 2 / h
                bw = (x2 - x1) / w
                bh = (y2 - y1) / h
                lines.append(f"{cls} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
                cls_counter[cls] += 1

            (labels_dir / f"{img_path.stem}.txt").write_text("\n".join(lines), encoding="utf-8")
            if lines:
                frames_with += 1
                if previews_saved < preview:
                    cv2.imwrite(str(preview_dir / img_path.name), res.plot())
                    previews_saved += 1

        done = min(start + len(chunk), len(images))
        if done % 50 == 0 or done == len(images):
            print(f"autolabeled {done}/{len(images)}")

    total = sum(cls_counter.values())
    print(f"frames: {len(images)} | with boxes: {frames_with} | boxes: {total}")
    for cls in sorted(cls_counter):
        print(f"  {NAMES.get(cls, cls)} ({cls}): {cls_counter[cls]}")
    print(f"images:  {images_dir.resolve()}")
    print(f"labels:  {labels_dir.resolve()}")
    print(f"preview: {preview_dir.resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect and auto-label a live AssaultCube dataset batch")
    parser.add_argument("--name", default=None, help="folder name under dataset/")
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--interval", type=float, default=0.4)
    parser.add_argument("--countdown", type=int, default=8)
    parser.add_argument("--capture-fps", type=int, default=60)
    parser.add_argument("--skip-collect", action="store_true", help="only run the requested post-processing steps")
    parser.add_argument("--autolabel", action="store_true")
    parser.add_argument("--weights", default=str(DEFAULT_WEIGHTS))
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--imgsz", type=int, default=1280)
    parser.add_argument("--device", default="0")
    parser.add_argument("--batch", type=int, default=2)
    parser.add_argument("--preview", type=int, default=40)
    args = parser.parse_args()

    root = dataset_root(args.name)
    root.mkdir(parents=True, exist_ok=True)
    print(f"dataset batch: {root.resolve()}")

    if not args.skip_collect:
        collect_images(root, args.count, args.interval, args.countdown, args.capture_fps)
    if args.autolabel:
        autolabel(root, args.weights, args.conf, args.imgsz, args.device, max(1, args.batch), args.preview)


if __name__ == "__main__":
    main()
