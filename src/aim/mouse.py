"""Вывод движения в мышь через WinAPI SendInput (относительное перемещение).

Относительная дельта (MOUSEEVENTF_MOVE без ABSOLUTE) — то, что нужно играм
с raw input вроде AssaultCube: игра реагирует на СМЕЩЕНИЕ мыши, а не на
позицию курсора. Поэтому SetCursorPos здесь не годится.

Только Windows.
"""

import ctypes
from ctypes import wintypes

MOUSEEVENTF_MOVE = 0x0001
INPUT_MOUSE = 0

ULONG_PTR = ctypes.c_size_t  # pointer-sized, корректно и на 64-бит


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("mi", _MOUSEINPUT)]

    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


_user32 = ctypes.windll.user32
# Явные типы аргументов — иначе на 64-бит указатели могут обрезаться.
_user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int)
_user32.SendInput.restype = wintypes.UINT
_user32.GetCursorPos.argtypes = (ctypes.POINTER(wintypes.POINT),)
_user32.GetCursorPos.restype = wintypes.BOOL


def move_relative(dx: int, dy: int) -> None:
    """Сдвинуть мышь на (dx, dy) относительно текущего положения."""
    if dx == 0 and dy == 0:
        return
    inp = _INPUT(type=INPUT_MOUSE)
    inp.mi = _MOUSEINPUT(dx, dy, 0, MOUSEEVENTF_MOVE, 0, 0)
    _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))


def get_cursor_pos() -> tuple[int, int]:
    pt = wintypes.POINT()
    _user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


if __name__ == "__main__":
    # Видимый тест: курсор обведёт маленький квадрат 80x80 и вернётся.
    import time

    print("cursor before:", get_cursor_pos())
    square = [(2, 0)] * 40 + [(0, 2)] * 40 + [(-2, 0)] * 40 + [(0, -2)] * 40
    for dx, dy in square:
        move_relative(dx, dy)
        time.sleep(0.005)
    print("cursor after:", get_cursor_pos())
