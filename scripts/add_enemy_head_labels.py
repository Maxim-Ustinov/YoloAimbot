"""Add generated EnemyHead YOLO labels from existing enemy boxes.

Class layout:
    0 enemy
    1 teammate
    2 EnemyHead

Example:
    python -m scripts.add_enemy_head_labels --labels C:\AI\dataset\live_20260610_1000\labels
"""

from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ENEMY_CLASS = 0
ENEMY_HEAD_CLASS = 2
CLASS_NAMES = ["enemy", "teammate", "EnemyHead"]
SERVICE_FILES = {"classes.txt", "labels.txt"}


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
        if len(parts) < 5:
            raise ValueError(f"expected 5 YOLO fields, got {len(parts)}")
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


def enemy_to_head(enemy: YoloBox, head_height_ratio: float, head_width_ratio: float) -> YoloBox:
    head_h = clamp(enemy.height * head_height_ratio)
    head_w = clamp(enemy.width * head_width_ratio)
    enemy_top = enemy.cy - enemy.height / 2
    head_cy = enemy_top + head_h / 2

    return YoloBox(
        cls=ENEMY_HEAD_CLASS,
        cx=clamp(enemy.cx),
        cy=clamp(head_cy),
        width=clamp(head_w),
        height=clamp(head_h),
    )


def backup_labels(labels_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = labels_dir.parent / f"{labels_dir.name}_backup_before_enemy_head_{timestamp}"
    shutil.copytree(labels_dir, backup_dir)
    return backup_dir


def write_class_files(labels_dir: Path) -> None:
    text = "\n".join(CLASS_NAMES) + "\n"
    for name in SERVICE_FILES:
        (labels_dir / name).write_text(text, encoding="utf-8")


def process_label_file(
    path: Path,
    head_height_ratio: float,
    head_width_ratio: float,
    replace_existing: bool,
) -> tuple[int, int, int]:
    lines = path.read_text(encoding="utf-8").splitlines()
    parsed: list[YoloBox] = []
    kept_lines: list[str] = []
    existing_heads = 0

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        box = YoloBox.parse(stripped)
        if box.cls == ENEMY_HEAD_CLASS:
            existing_heads += 1
            if replace_existing:
                continue
        parsed.append(box)
        kept_lines.append(box.format())

    enemies = [box for box in parsed if box.cls == ENEMY_CLASS]
    if existing_heads and not replace_existing:
        path.write_text("\n".join(kept_lines) + ("\n" if kept_lines else ""), encoding="utf-8")
        return len(enemies), 0, existing_heads

    generated = [enemy_to_head(enemy, head_height_ratio, head_width_ratio) for enemy in enemies]
    output_lines = kept_lines + [box.format() for box in generated]
    path.write_text("\n".join(output_lines) + ("\n" if output_lines else ""), encoding="utf-8")
    return len(enemies), len(generated), existing_heads


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate EnemyHead labels from enemy boxes")
    parser.add_argument("--labels", default=r"C:\AI\dataset\live_20260610_1000\labels")
    parser.add_argument("--head-height-ratio", type=float, default=0.10)
    parser.add_argument("--head-width-ratio", type=float, default=0.55)
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="remove existing class 2 boxes before generating new ones",
    )
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()

    labels_dir = Path(args.labels)
    if not labels_dir.exists():
        raise FileNotFoundError(f"labels directory not found: {labels_dir}")

    if not args.no_backup:
        backup_dir = backup_labels(labels_dir)
        print(f"backup: {backup_dir}")

    write_class_files(labels_dir)

    files = sorted(path for path in labels_dir.glob("*.txt") if path.name.lower() not in SERVICE_FILES)
    total_enemies = 0
    total_generated = 0
    total_existing_heads = 0
    processed = 0

    for path in files:
        enemies, generated, existing_heads = process_label_file(
            path,
            head_height_ratio=args.head_height_ratio,
            head_width_ratio=args.head_width_ratio,
            replace_existing=args.replace_existing,
        )
        total_enemies += enemies
        total_generated += generated
        total_existing_heads += existing_heads
        processed += 1

    print(f"files: {processed}")
    print(f"enemy boxes: {total_enemies}")
    print(f"generated EnemyHead boxes: {total_generated}")
    print(f"existing EnemyHead boxes kept: {0 if args.replace_existing else total_existing_heads}")
    print(f"labels: {labels_dir}")


if __name__ == "__main__":
    main()
