r"""
Этап 2: проверка захвата экрана.
Запуск из корня C:\AI:  python -m scripts.capture_fps

Меряет FPS захвата и сохраняет один кадр в out\capture_test.png,
чтобы глазами убедиться, что захватывается именно экран.

Сообщения print — на английском намеренно: при перекодировке вывода в
Windows-консоль кириллица коверкается. Комментарии и docstring — на русском.

Примечание: при выходе bettercam печатает безвредный трейсбек
"Exception ignored in __del__ ... access violation" — это финализация
COM-объектов библиотеки на завершении процесса, на результат не влияет.
"""

import time
from pathlib import Path

import cv2

from src.capture import ScreenCapture

FRAMES = 200
OUT = Path("out/capture_test.png")


def main() -> None:
    cap = ScreenCapture(region=None, target_fps=240)
    cap.start()
    try:
        # прогрев: дождаться первого кадра
        frame = cap.latest_frame()
        h, w = frame.shape[:2]

        t0 = time.perf_counter()
        for _ in range(FRAMES):
            frame = cap.latest_frame()
        dt = time.perf_counter() - t0

        print(f"captured {FRAMES} frames in {dt:.2f}s  ->  {FRAMES / dt:.1f} FPS")
        print(f"frame size: {w}x{h}, channels: {frame.shape[2]} (BGR)")

        OUT.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(OUT), frame)
        print(f"frame saved: {OUT.resolve()}")
    finally:
        cap.close()


if __name__ == "__main__":
    main()
