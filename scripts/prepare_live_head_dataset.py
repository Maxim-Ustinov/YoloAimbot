"""Prepare a YOLO train/val split for the live 3-class AssaultCube dataset."""

from __future__ import annotations

import argparse
import random
import shutil
from collections import Counter
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
CLASS_NAMES = ["enemy", "teammate", "EnemyHead"]


def has_label(label_path: Path) -> bool:
    if not label_path.exists():
        return False
    return bool(label_path.read_text(encoding="utf-8").strip())


def split_images(images: list[Path], labels_dir: Path, val_fraction: float, seed: int) -> tuple[list[Path], list[Path]]:
    positives = [path for path in images if has_label(labels_dir / f"{path.stem}.txt")]
    backgrounds = [path for path in images if path not in set(positives)]

    rng = random.Random(seed)
    rng.shuffle(positives)
    rng.shuffle(backgrounds)

    def split_group(group: list[Path]) -> tuple[list[Path], list[Path]]:
        val_count = max(1, round(len(group) * val_fraction)) if group else 0
        return group[val_count:], group[:val_count]

    train_pos, val_pos = split_group(positives)
    train_bg, val_bg = split_group(backgrounds)
    train = train_pos + train_bg
    val = val_pos + val_bg
    rng.shuffle(train)
    rng.shuffle(val)
    return train, val


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def copy_split(images: list[Path], source_labels: Path, out_root: Path, split: str) -> Counter[int]:
    images_out = out_root / "images" / split
    labels_out = out_root / "labels" / split
    images_out.mkdir(parents=True, exist_ok=True)
    labels_out.mkdir(parents=True, exist_ok=True)

    counts: Counter[int] = Counter()
    for image in images:
        shutil.copy2(image, images_out / image.name)
        source_label = source_labels / f"{image.stem}.txt"
        target_label = labels_out / f"{image.stem}.txt"
        if source_label.exists():
            text = source_label.read_text(encoding="utf-8")
            target_label.write_text(text, encoding="utf-8")
            for line in text.splitlines():
                stripped = line.strip()
                if stripped:
                    counts[int(float(stripped.split()[0]))] += 1
        else:
            target_label.write_text("", encoding="utf-8")
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
    parser = argparse.ArgumentParser(description="Prepare live AssaultCube head dataset")
    parser.add_argument("--source", default=r"C:\AI\dataset\live_20260610_1000")
    parser.add_argument("--out", default=r"C:\AI\dataset\live_head_3cls")
    parser.add_argument("--val", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=20260610)
    args = parser.parse_args()

    source = Path(args.source)
    out = Path(args.out)
    images_dir = source / "images"
    labels_dir = source / "labels"
    images = sorted(path for path in images_dir.iterdir() if path.suffix.lower() in IMAGE_EXTS)
    if not images:
        raise FileNotFoundError(f"no images found in {images_dir}")
    if not labels_dir.exists():
        raise FileNotFoundError(f"labels directory not found: {labels_dir}")

    reset_dir(out / "images" / "train")
    reset_dir(out / "images" / "val")
    reset_dir(out / "labels" / "train")
    reset_dir(out / "labels" / "val")

    train, val = split_images(images, labels_dir, args.val, args.seed)
    train_counts = copy_split(train, labels_dir, out, "train")
    val_counts = copy_split(val, labels_dir, out, "val")
    yaml_path = write_yaml(out)

    print(f"source images: {len(images)}")
    print(f"train images: {len(train)} | labels: {dict(sorted(train_counts.items()))}")
    print(f"val images: {len(val)} | labels: {dict(sorted(val_counts.items()))}")
    print(f"yaml: {yaml_path}")


if __name__ == "__main__":
    main()
