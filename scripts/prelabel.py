r"""
Этап 3.2: авто-предразметка датасета.

Предобученная YOLO (COCO) находит на кадрах класс 'person' и сохраняет боксы
как наш класс 0 = 'enemy' в формате YOLO. Головы (класс 1 = 'head') ты добавишь
вручную в инструменте разметки на этапе ревью.

Запуск из корня C:\AI:
    python -m scripts.prelabel
    python -m scripts.prelabel --model yolo11x.pt --conf 0.2   # выше recall

Результат:
  datasets/labels/frame_XXXXX.txt   — лейблы YOLO (класс 0=enemy)
  datasets/labels/classes.txt       — имена классов (enemy, head)
  datasets/prelabel_preview/*.jpg   — несколько кадров с нарисованными боксами
                                      (глазами проверить качество предразметки)
"""

import argparse
from pathlib import Path

import cv2
from ultralytics import YOLO

RAW = Path("datasets/raw")
LABELS = Path("datasets/labels")
PREVIEW = Path("datasets/prelabel_preview")

PERSON_CLASS = 0  # 'person' в COCO
ENEMY_CLASS = 0   # наш класс 'enemy'


def main() -> None:
    ap = argparse.ArgumentParser(description="Auto pre-label frames with a pretrained YOLO")
    ap.add_argument("--model", default="yolo11m.pt", help="предобученная модель COCO")
    ap.add_argument("--conf", type=float, default=0.25, help="порог уверенности")
    ap.add_argument("--preview", type=int, default=12, help="сколько превью сохранить")
    args = ap.parse_args()

    images = sorted(RAW.glob("frame_*.jpg"))
    if not images:
        print("нет кадров в datasets/raw")
        return

    LABELS.mkdir(parents=True, exist_ok=True)
    PREVIEW.mkdir(parents=True, exist_ok=True)
    (LABELS / "classes.txt").write_text("enemy\nhead\n", encoding="utf-8")

    model = YOLO(args.model)

    total_boxes = 0
    frames_with = 0
    previews_saved = 0

    for img_path in images:
        res = model.predict(
            str(img_path), conf=args.conf, classes=[PERSON_CLASS], verbose=False
        )[0]
        h, w = res.orig_shape

        lines = []
        for box in res.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            cx = (x1 + x2) / 2 / w
            cy = (y1 + y2) / 2 / h
            bw = (x2 - x1) / w
            bh = (y2 - y1) / h
            lines.append(f"{ENEMY_CLASS} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")

        (LABELS / f"{img_path.stem}.txt").write_text("\n".join(lines), encoding="utf-8")
        total_boxes += len(lines)
        if lines:
            frames_with += 1
            if previews_saved < args.preview:
                cv2.imwrite(str(PREVIEW / img_path.name), res.plot())
                previews_saved += 1

    print(f"frames: {len(images)} | with boxes: {frames_with} | total boxes: {total_boxes}")
    print(f"labels:  {LABELS.resolve()}")
    print(f"preview: {PREVIEW.resolve()} ({previews_saved} files)")


if __name__ == "__main__":
    main()
