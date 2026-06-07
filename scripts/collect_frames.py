r"""
Этап 3: сбор кадров для датасета.

Запуск из корня C:\AI:
    python -m scripts.collect_frames                      # 300 кадров, каждые 0.4с
    python -m scripts.collect_frames --count 500 --interval 0.3

Как пользоваться:
  1) Запусти AssaultCube в ОКОННОМ / БЕЗРАМОЧНОМ режиме на весь экран
     (полноэкранный «эксклюзив» может ломать захват через Desktop Duplication).
  2) Заведи матч с ботами.
  3) Запусти скрипт — пойдёт обратный отсчёт, успей переключиться в игру.
  4) Играй: разные карты, дистанции, ракурсы, освещение — чем разнообразнее
     кадры, тем лучше обучится модель.

Кадры пишутся в datasets\raw\ как frame_XXXXX.jpg. Можно запускать несколько
раз (на разных картах) — нумерация продолжается, старое не затирается.
"""

import argparse
import time
from pathlib import Path

import cv2

from src.capture import ScreenCapture

OUT_DIR = Path("datasets/raw")


def _next_index(out_dir: Path) -> int:
    """Следующий свободный номер кадра (чтобы дописывать к уже собранным)."""
    existing = sorted(out_dir.glob("frame_*.jpg"))
    if not existing:
        return 0
    return int(existing[-1].stem.split("_")[1]) + 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect screen frames for the dataset")
    parser.add_argument("--count", type=int, default=300, help="сколько кадров сохранить")
    parser.add_argument("--interval", type=float, default=0.4, help="пауза между кадрами, сек")
    parser.add_argument("--countdown", type=int, default=5, help="отсчёт перед стартом, сек")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    start_idx = _next_index(OUT_DIR)

    for s in range(args.countdown, 0, -1):
        print(f"start in {s}... (switch to the game)")
        time.sleep(1)

    cap = ScreenCapture(region=None, target_fps=60)
    cap.start()
    try:
        for i in range(args.count):
            frame = cap.latest_frame()
            path = OUT_DIR / f"frame_{start_idx + i:05d}.jpg"
            cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            if (i + 1) % 20 == 0:
                print(f"saved {i + 1}/{args.count}")
            time.sleep(args.interval)
        print(f"done: {args.count} frames -> {OUT_DIR.resolve()}")
    finally:
        cap.close()


if __name__ == "__main__":
    main()
