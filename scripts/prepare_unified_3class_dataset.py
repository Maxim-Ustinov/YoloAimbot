"""Build the single production 3-class AssaultCube dataset.

The output is a clean YOLO dataset used to train one model:
    0 enemy
    1 teammate
    2 EnemyHead

Old 2-class sources are excluded by default, because every visible class must
be labeled for YOLO training. Mixing images with missing EnemyHead labels, or
generated approximate heads, teaches the model that many real heads are
background. Pass --include-generated-heads only for a quick bootstrap dataset.
"""

from __future__ import annotations

import argparse
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
SERVICE_FILES = {"classes.txt", "labels.txt"}
CLASS_NAMES = ["enemy", "teammate", "EnemyHead"]
ENEMY_CLASS = 0
ENEMY_HEAD_CLASS = 2


@dataclass(frozen=True)
class Source:
    name: str
    root: Path
    split: str
    allow_generated_heads: bool = False


@dataclass(frozen=True)
class YoloBox:
    cls: int
    cx: float
    cy: float
    width: float
    height: float

    @classmethod
    def parse(cls, line: str) -> "YoloBox":
        parts = line.split()
        return cls(
            cls=int(float(parts[0])),
            cx=float(parts[1]),
            cy=float(parts[2]),
            width=float(parts[3]),
            height=float(parts[4]),
        )

    def format(self) -> str:
        return f"{self.cls} {self.cx:.6f} {self.cy:.6f} {self.width:.6f} {self.height:.6f}"


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def generated_head(enemy: YoloBox, height_ratio: float, width_ratio: float) -> YoloBox:
    head_h = clamp(enemy.height * height_ratio)
    head_w = clamp(enemy.width * width_ratio)
    top = enemy.cy - enemy.height / 2
    return YoloBox(
        cls=ENEMY_HEAD_CLASS,
        cx=clamp(enemy.cx),
        cy=clamp(top + head_h / 2),
        width=head_w,
        height=head_h,
    )


def read_boxes(path: Path) -> list[YoloBox]:
    if not path.exists():
        return []
    boxes: list[YoloBox] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if stripped:
            boxes.append(YoloBox.parse(stripped))
    return boxes


def source_has_heads(labels_dir: Path) -> bool:
    for path in labels_dir.glob("*.txt"):
        if path.name.lower() in SERVICE_FILES:
            continue
        if any(box.cls == ENEMY_HEAD_CLASS for box in read_boxes(path)):
            return True
    return False


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def prefixed_name(source: Source, image: Path) -> str:
    return f"{source.name}__{image.name}"


def copy_source(
    source: Source,
    out_root: Path,
    head_height_ratio: float,
    head_width_ratio: float,
) -> Counter[int]:
    images_dir = source.root / "images"
    labels_dir = source.root / "labels"
    if not images_dir.exists():
        raise FileNotFoundError(f"images directory not found: {images_dir}")
    if not labels_dir.exists():
        raise FileNotFoundError(f"labels directory not found: {labels_dir}")

    split_images = out_root / "images" / source.split
    split_labels = out_root / "labels" / source.split
    split_images.mkdir(parents=True, exist_ok=True)
    split_labels.mkdir(parents=True, exist_ok=True)

    has_heads = source_has_heads(labels_dir)
    if not has_heads and not source.allow_generated_heads:
        print(f"{source.name} -> skipped: no EnemyHead labels")
        return counts

    add_generated_heads = not has_heads
    counts: Counter[int] = Counter()
    images = sorted(path for path in images_dir.iterdir() if path.suffix.lower() in IMAGE_EXTS)
    for image in images:
        target_image = split_images / prefixed_name(source, image)
        shutil.copy2(image, target_image)

        boxes = read_boxes(labels_dir / f"{image.stem}.txt")
        if add_generated_heads:
            enemies = [box for box in boxes if box.cls == ENEMY_CLASS]
            boxes.extend(generated_head(box, head_height_ratio, head_width_ratio) for box in enemies)

        for box in boxes:
            counts[box.cls] += 1

        target_label = split_labels / f"{target_image.stem}.txt"
        text = "\n".join(box.format() for box in boxes)
        target_label.write_text(text + ("\n" if text else ""), encoding="utf-8")
    return counts


def write_yaml(out_root: Path) -> Path:
    yaml_path = out_root / "data.yaml"
    names = ", ".join(repr(name) for name in CLASS_NAMES)
    yaml_path.write_text(
        "\n".join(
            [
                f"path: {out_root.as_posix()}",
                "train: images/train",
                "val: images/val",
                f"nc: {len(CLASS_NAMES)}",
                f"names: [{names}]",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return yaml_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare the unified production AssaultCube dataset")
    parser.add_argument("--out", default=r"C:\AI\dataset\assaultcube_unified_3cls")
    parser.add_argument("--head-height-ratio", type=float, default=0.10)
    parser.add_argument("--head-width-ratio", type=float, default=0.55)
    parser.add_argument(
        "--include-generated-heads",
        action="store_true",
        help="also include old 2-class sources with generated approximate EnemyHead labels",
    )
    args = parser.parse_args()

    out_root = Path(args.out)
    reset_dir(out_root / "images" / "train")
    reset_dir(out_root / "images" / "val")
    reset_dir(out_root / "labels" / "train")
    reset_dir(out_root / "labels" / "val")

    sources = [
        Source(
            "base_train",
            Path(r"C:\AI\dataset\train"),
            "train",
            allow_generated_heads=args.include_generated_heads,
        ),
        Source("live_20260610_1000", Path(r"C:\AI\dataset\live_20260610_1000"), "train"),
        Source("base_valid", Path(r"C:\AI\dataset\valid"), "val"),
    ]

    total: Counter[int] = Counter()
    for source in sources:
        counts = copy_source(source, out_root, args.head_height_ratio, args.head_width_ratio)
        total.update(counts)
        print(f"{source.name} -> {source.split}: {dict(sorted(counts.items()))}")

    yaml_path = write_yaml(out_root)
    print(f"total: {dict(sorted(total.items()))}")
    print(f"yaml: {yaml_path}")


if __name__ == "__main__":
    main()
