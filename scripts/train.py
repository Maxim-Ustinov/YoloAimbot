r"""
Этап 4: обучение детектора (YOLO11) на собранном датасете.

Запуск из корня C:\AI:
    python -m scripts.train                          # imgsz=640, 100 эпох
    python -m scripts.train --imgsz 1280 --epochs 150

Датасет описан в dataset/data_full.yaml (классы: enemy, teammate).
Лучшие веса: runs/detect/<name>/weights/best.pt
"""

import argparse

from ultralytics import YOLO


def main() -> None:
    ap = argparse.ArgumentParser(description="Train a YOLO detector on the AssaultCube dataset")
    ap.add_argument("--model", default="yolo11m.pt", help="стартовые веса")
    ap.add_argument("--data", default="dataset/data_full.yaml", help="конфиг датасета")
    ap.add_argument("--epochs", type=int, default=100)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--device", default="0", help="GPU id или 'cpu'")
    ap.add_argument("--name", default=None, help="имя runs/detect/<name>")
    ap.add_argument("--project", default=None, help="папка проекта для runs")
    ap.add_argument("--patience", type=int, default=100)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--cache", action="store_true", help="кэшировать датасет в RAM/на диск средствами Ultralytics")
    ap.add_argument("--cos-lr", action="store_true", help="cosine LR schedule")
    ap.add_argument("--close-mosaic", type=int, default=10)
    ap.add_argument("--save-period", type=int, default=-1)
    ap.add_argument("--exist-ok", action="store_true")
    ap.add_argument("--resume", action="store_true", help="resume training from a last.pt checkpoint")
    ap.add_argument("--lr0", type=float, default=0.01, help="initial learning rate")
    ap.add_argument("--lrf", type=float, default=0.01, help="final learning rate fraction")
    ap.add_argument("--optimizer", default="auto", help="auto|SGD|Adam|AdamW (auto игнорирует lr0)")
    ap.add_argument("--warmup-epochs", type=float, default=3.0)
    ap.add_argument("--mosaic", type=float, default=1.0, help="вероятность mosaic-аугментации")
    ap.add_argument("--scale", type=float, default=0.5, help="диапазон случайного масштаба")
    ap.add_argument("--erasing", type=float, default=0.4, help="вероятность random erasing")
    args = ap.parse_args()

    model = YOLO(args.model)
    if args.resume:
        model.train(resume=True)
        return

    model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        name=args.name,
        project=args.project,
        patience=args.patience,
        workers=args.workers,
        cache=args.cache,
        cos_lr=args.cos_lr,
        close_mosaic=args.close_mosaic,
        save_period=args.save_period,
        exist_ok=args.exist_ok,
        lr0=args.lr0,
        lrf=args.lrf,
        optimizer=args.optimizer,
        warmup_epochs=args.warmup_epochs,
        mosaic=args.mosaic,
        scale=args.scale,
        erasing=args.erasing,
        amp=True,
        plots=True,
    )


if __name__ == "__main__":
    main()
