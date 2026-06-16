"""Prepare a train/val split from a manually corrected MakeSense export."""

from __future__ import annotations

import argparse
import random
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
CLASS_NAMES = ["enemy", "teammate", "EnemyHead"]
SERVICE_FILES = {"classes.txt", "labels.txt"}


@dataclass(frozen=True)
class Sample:
    image: Path
    label: Path | None
    source_dataset: str
    has_objects: bool


def reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def clean_label(path: Path | None) -> tuple[list[str], Counter[int], int]:
    if path is None or not path.exists() or path.name.lower() in SERVICE_FILES:
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
        if not (0.0 <= cx <= 1.0 and 0.0 <= cy <= 1.0 and 0.0 < width <= 1.0 and 0.0 < height <= 1.0):
            dropped += 1
            continue
        lines.append(f"{cls} {cx:.6f} {cy:.6f} {width:.6f} {height:.6f}")
        counts[cls] += 1
    return lines, counts, dropped


def source_from_name(image: Path) -> str:
    return image.name.split("__", 1)[0] if "__" in image.name else "unknown"


def collect_samples(images_dir: Path, labels_dir: Path) -> list[Sample]:
    images = sorted(path for path in images_dir.iterdir() if path.suffix.lower() in IMAGE_EXTS)
    if not images:
        raise FileNotFoundError(f"no images found in {images_dir}")
    samples: list[Sample] = []
    for image in images:
        label = labels_dir / f"{image.stem}.txt"
        label_path = label if label.exists() else None
        lines, _, _ = clean_label(label_path)
        samples.append(
            Sample(
                image=image,
                label=label_path,
                source_dataset=source_from_name(image),
                has_objects=bool(lines),
            )
        )
    return samples


def split_samples(samples: list[Sample], val_fraction: float, seed: int) -> tuple[list[Sample], list[Sample]]:
    groups: dict[tuple[str, bool], list[Sample]] = defaultdict(list)
    for sample in samples:
        groups[(sample.source_dataset, sample.has_objects)].append(sample)

    rng = random.Random(seed)
    train: list[Sample] = []
    val: list[Sample] = []
    for group in groups.values():
        rng.shuffle(group)
        val_count = max(1, round(len(group) * val_fraction)) if len(group) > 1 else 0
        val.extend(group[:val_count])
        train.extend(group[val_count:])
    rng.shuffle(train)
    rng.shuffle(val)
    return train, val


def copy_split(samples: list[Sample], out_root: Path, split: str) -> tuple[Counter[int], int, int]:
    images_out = out_root / "images" / split
    labels_out = out_root / "labels" / split
    images_out.mkdir(parents=True, exist_ok=True)
    labels_out.mkdir(parents=True, exist_ok=True)

    counts: Counter[int] = Counter()
    dropped = 0
    empty = 0
    for sample in samples:
        target_image = images_out / sample.image.name
        target_label = labels_out / f"{sample.image.stem}.txt"
        shutil.copy2(sample.image, target_image)

        lines, label_counts, label_dropped = clean_label(sample.label)
        counts.update(label_counts)
        dropped += label_dropped
        if not lines:
            empty += 1
        target_label.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return counts, dropped, empty


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


def write_class_files(out_root: Path) -> None:
    text = "\n".join(CLASS_NAMES) + "\n"
    (out_root / "classes.txt").write_text(text, encoding="utf-8")
    for split in ("train", "val"):
        labels_dir = out_root / "labels" / split
        labels_dir.mkdir(parents=True, exist_ok=True)
        (labels_dir / "classes.txt").write_text(text, encoding="utf-8")
        (labels_dir / "labels.txt").write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare corrected relabel train/val split")
    parser.add_argument("--root", default=r"C:\AI\dataset\aimify_relabel_20260611_all")
    parser.add_argument("--labels", required=True)
    parser.add_argument("--out", default=r"C:\AI\dataset\aimify_relabel_20260611_corrected_split")
    parser.add_argument("--val", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=20260611)
    args = parser.parse_args()

    if not 0.0 < args.val < 1.0:
        raise ValueError("--val must be between 0 and 1")

    root = Path(args.root)
    images_dir = root / "images"
    labels_dir = Path(args.labels)
    out_root = Path(args.out)
    if not labels_dir.exists():
        raise FileNotFoundError(f"labels directory not found: {labels_dir}")

    reset_dir(out_root / "images" / "train")
    reset_dir(out_root / "images" / "val")
    reset_dir(out_root / "labels" / "train")
    reset_dir(out_root / "labels" / "val")

    samples = collect_samples(images_dir, labels_dir)
    train, val = split_samples(samples, args.val, args.seed)
    train_counts, train_dropped, train_empty = copy_split(train, out_root, "train")
    val_counts, val_dropped, val_empty = copy_split(val, out_root, "val")
    write_class_files(out_root)
    yaml_path = write_yaml(out_root)

    print(f"samples: {len(samples)}")
    print(f"train images: {len(train)} | labels: {dict(sorted(train_counts.items()))} | empty: {train_empty} | dropped: {train_dropped}")
    print(f"val images: {len(val)} | labels: {dict(sorted(val_counts.items()))} | empty: {val_empty} | dropped: {val_dropped}")
    print(f"yaml: {yaml_path}")


if __name__ == "__main__":
    main()
