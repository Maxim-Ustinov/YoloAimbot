r"""
Авто-разметка: seed-модель расставляет лейблы для изображений в train/ и test/
(сейчас они без разметки — лейблы были удалены).

Запуск из корня C:\AI:
    python -m scripts.autolabel
    python -m scripts.autolabel --conf 0.35

Для каждого изображения пишет YOLO-txt в dataset/<split>/labels/ и сохраняет
несколько превью с боксами в dataset/<split>/autolabel_preview/.

ВАЖНО: это ЧЕРНОВИК. Предсказания модели надо проверить и поправить
(в makesense) перед тем, как дообучать на них — иначе модель учится на своих
же ошибках. И test для честных метрик должен остаться ручным.
"""

import argparse
from collections import Counter
from pathlib import Path

import cv2
from ultralytics import YOLO

from src.detect.detector import DEFAULT_WEIGHTS

WEIGHTS = DEFAULT_WEIGHTS
SPLITS = ["train", "test"]
NAMES = {0: "enemy", 1: "teammate"}
EXTS = {".jpg", ".jpeg", ".png"}


def main() -> None:
    ap = argparse.ArgumentParser(description="Auto-label train/test images with the seed model")
    ap.add_argument("--weights", default=str(WEIGHTS))
    ap.add_argument("--conf", type=float, default=0.4, help="порог уверенности")
    ap.add_argument("--preview", type=int, default=8, help="сколько превью на сплит")
    ap.add_argument("--splits", nargs="+", default=SPLITS, help="какие сплиты размечать (по умолчанию train test)")
    args = ap.parse_args()

    model = YOLO(args.weights)

    for split in args.splits:
        img_dir = Path(f"dataset/{split}/images")
        lbl_dir = Path(f"dataset/{split}/labels")
        prev_dir = Path(f"dataset/{split}/autolabel_preview")
        images = sorted(p for p in img_dir.glob("*") if p.suffix.lower() in EXTS)
        if not images:
            print(f"[{split}] нет изображений в {img_dir}")
            continue
        lbl_dir.mkdir(parents=True, exist_ok=True)
        prev_dir.mkdir(parents=True, exist_ok=True)

        cls_counter: Counter = Counter()
        frames_with = 0
        previews = 0

        for img_path in images:
            res = model.predict(str(img_path), conf=args.conf, verbose=False)[0]
            h, w = res.orig_shape
            lines = []
            for b in res.boxes:
                cls = int(b.cls[0])
                x1, y1, x2, y2 = b.xyxy[0].tolist()
                cx = (x1 + x2) / 2 / w
                cy = (y1 + y2) / 2 / h
                bw = (x2 - x1) / w
                bh = (y2 - y1) / h
                lines.append(f"{cls} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
                cls_counter[cls] += 1
            (lbl_dir / f"{img_path.stem}.txt").write_text("\n".join(lines), encoding="utf-8")
            if lines:
                frames_with += 1
                if previews < args.preview:
                    cv2.imwrite(str(prev_dir / img_path.name), res.plot())
                    previews += 1

        total = sum(cls_counter.values())
        print(f"[{split}] кадров: {len(images)} | с объектами: {frames_with} | боксов: {total}")
        for c in sorted(cls_counter):
            print(f"    {NAMES.get(c, c)} (id {c}): {cls_counter[c]}")
        print(f"    превью: {prev_dir.resolve()} ({previews} шт)")


if __name__ == "__main__":
    main()
