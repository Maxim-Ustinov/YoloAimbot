"""Build a clean YOLO train/val split from manually checked 3-class sources.

This dataset is intended for AImify training:
    0 enemy
    1 teammate
    2 EnemyHead

Only sources that already have real EnemyHead labels should be passed here.
The script does not generate synthetic head boxes.
"""

from __future__ import annotations

import argparse
import random
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
CLASS_NAMES = ["enemy", "teammate", "EnemyHead"]
SERVICE_FILES = {"classes.txt", "labels.txt"}


@dataclass(frozen=True)
class Source:
    name: str
    root: Path


@dataclass(frozen=True)
class Sample:
    source: Source
    image: Path
    label: Path


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def prefixed_stem(sample: Sample) -> str:
    return f"{sample.source.name}__{sample.image.stem}"


def label_for_image(labels_dir: Path, image: Path) -> Path:
    return labels_dir / f"{image.stem}.txt"


def read_clean_label(path: Path) -> tuple[list[str], Counter[int], int]:
    if not path.exists() or path.name.lower() in SERVICE_FILES:
        return [], Counter(), 0

    lines: list[str] = []
    counts: Counter[int] = Counter()
    dropped = 0
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = raw.strip()
        if not stripped:
            continue

        parts = stripped.split()
        if len(parts) < 5:
            dropped += 1
            continue

        try:
            cls = int(float(parts[0]))
            cx, cy, width, height = (float(value) for value in parts[1:5])
        except ValueError:
            dropped += 1
            continue

        if cls < 0 or cls >= len(CLASS_NAMES):
            dropped += 1
            continue
        if width <= 0.0 or height <= 0.0:
            dropped += 1
            continue
        if not (0.0 <= cx <= 1.0 and 0.0 <= cy <= 1.0 and 0.0 < width <= 1.0 and 0.0 < height <= 1.0):
            dropped += 1
            continue

        lines.append(f"{cls} {cx:.6f} {cy:.6f} {width:.6f} {height:.6f}")
        counts[cls] += 1

    return lines, counts, dropped


def collect_samples(sources: list[Source]) -> list[Sample]:
    samples: list[Sample] = []
    for source in sources:
        images_dir = source.root / "images"
        labels_dir = source.root / "labels"
        if not images_dir.exists():
            raise FileNotFoundError(f"images directory not found: {images_dir}")
        if not labels_dir.exists():
            raise FileNotFoundError(f"labels directory not found: {labels_dir}")

        images = sorted(path for path in images_dir.iterdir() if path.suffix.lower() in IMAGE_EXTS)
        samples.extend(Sample(source, image, label_for_image(labels_dir, image)) for image in images)
    return samples


def sample_has_objects(sample: Sample) -> bool:
    lines, _, _ = read_clean_label(sample.label)
    return bool(lines)


def split_samples(samples: list[Sample], val_fraction: float, seed: int) -> tuple[list[Sample], list[Sample]]:
    positives = [sample for sample in samples if sample_has_objects(sample)]
    backgrounds = [sample for sample in samples if sample not in set(positives)]

    rng = random.Random(seed)
    rng.shuffle(positives)
    rng.shuffle(backgrounds)

    def split_group(group: list[Sample]) -> tuple[list[Sample], list[Sample]]:
        if not group:
            return [], []
        val_count = max(1, round(len(group) * val_fraction))
        return group[val_count:], group[:val_count]

    train_pos, val_pos = split_group(positives)
    train_bg, val_bg = split_group(backgrounds)
    train = train_pos + train_bg
    val = val_pos + val_bg
    rng.shuffle(train)
    rng.shuffle(val)
    return train, val


def copy_split(samples: list[Sample], out_root: Path, split: str) -> tuple[Counter[int], int]:
    images_out = out_root / "images" / split
    labels_out = out_root / "labels" / split
    images_out.mkdir(parents=True, exist_ok=True)
    labels_out.mkdir(parents=True, exist_ok=True)

    counts: Counter[int] = Counter()
    dropped = 0
    for sample in samples:
        target_stem = prefixed_stem(sample)
        target_image = images_out / f"{target_stem}{sample.image.suffix.lower()}"
        target_label = labels_out / f"{target_stem}.txt"

        shutil.copy2(sample.image, target_image)
        lines, label_counts, label_dropped = read_clean_label(sample.label)
        counts.update(label_counts)
        dropped += label_dropped
        target_label.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    return counts, dropped


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
    parser = argparse.ArgumentParser(description="Prepare a clean manually labeled AImify 3-class dataset")
    parser.add_argument("--out", default=r"C:\AI\dataset\aimify_gen1_clean")
    parser.add_argument("--val", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=20260610)
    args = parser.parse_args()

    if not 0.0 < args.val < 1.0:
        raise ValueError("--val must be between 0 and 1")

    sources = [
        Source("live_20260610_1000", Path(r"C:\AI\dataset\live_20260610_1000")),
        Source("base_valid", Path(r"C:\AI\dataset\valid")),
    ]

    out_root = Path(args.out)
    reset_dir(out_root / "images" / "train")
    reset_dir(out_root / "images" / "val")
    reset_dir(out_root / "labels" / "train")
    reset_dir(out_root / "labels" / "val")

    samples = collect_samples(sources)
    train, val = split_samples(samples, args.val, args.seed)
    train_counts, train_dropped = copy_split(train, out_root, "train")
    val_counts, val_dropped = copy_split(val, out_root, "val")
    yaml_path = write_yaml(out_root)

    print(f"sources: {', '.join(source.name for source in sources)}")
    print(f"samples: {len(samples)}")
    print(f"train images: {len(train)} | labels: {dict(sorted(train_counts.items()))} | dropped bad lines: {train_dropped}")
    print(f"val images: {len(val)} | labels: {dict(sorted(val_counts.items()))} | dropped bad lines: {val_dropped}")
    print(f"yaml: {yaml_path}")


if __name__ == "__main__":
    main()
