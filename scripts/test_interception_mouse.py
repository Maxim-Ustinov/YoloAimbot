"""Видимый тест Interception mouse backend.

Запуск из C:\\AI:
    .\\.venv\\Scripts\\python -m scripts.test_interception_mouse --mouse-index 1

Если identify.exe показал другой номер, подставь его в --mouse-index.
"""

import argparse
import time

from src.aim.interception_mouse import InterceptionMouse
from src.aim.mouse import get_cursor_pos


def main() -> None:
    parser = argparse.ArgumentParser(description="Test Interception relative mouse movement")
    parser.add_argument("--mouse-index", type=int, default=1, help="номер из INTERCEPTION_MOUSE(index)")
    parser.add_argument("--step", type=int, default=4, help="размер одного шага")
    parser.add_argument("--count", type=int, default=40, help="шагов на сторону квадрата")
    parser.add_argument("--delay", type=float, default=0.005, help="пауза между шагами")
    args = parser.parse_args()

    square = (
        [(args.step, 0)] * args.count
        + [(0, args.step)] * args.count
        + [(-args.step, 0)] * args.count
        + [(0, -args.step)] * args.count
    )

    print(f"using INTERCEPTION_MOUSE({args.mouse_index})")
    print("cursor before:", get_cursor_pos())
    sent = 0
    with InterceptionMouse(mouse_index=args.mouse_index) as mouse:
        for dx, dy in square:
            sent += mouse.move_relative(dx, dy)
            time.sleep(args.delay)
    print("sent strokes:", sent)
    print("cursor after:", get_cursor_pos())


if __name__ == "__main__":
    main()
