"""Чтение состояния клавиши/кнопки активации наводки (Windows, GetAsyncKeyState).

Нужно для режима HOLD: наводка работает, только пока зажата activation_key.
"""

import ctypes

_user32 = ctypes.windll.user32

# Имена из конфига -> виртуальные коды клавиш Windows.
_NAMED = {
    "mouse_left": 0x01,
    "leftmousebutton": 0x01,
    "mouse_right": 0x02,
    "rightmousebutton": 0x02,
    "mouse_middle": 0x04,
    "middlemousebutton": 0x04,
    "mouse_x1": 0x05,
    "mouse_x2": 0x06,
    "shift": 0x10,
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "tab": 0x09,
    "space": 0x20,
    "caps": 0x14,
    "escape": 0x1B,
    "esc": 0x1B,
}
for _i in range(1, 13):
    _NAMED[f"f{_i}"] = 0x6F + _i


def _vk(key: str) -> int | None:
    key = key.strip().lower().replace(" ", "").replace("-", "_")
    if key in _NAMED:
        return _NAMED[key]
    if len(key) == 1:
        return ord(key.upper())  # A..Z, 0..9
    return None


def is_down(key: str) -> bool:
    """True, пока клавиша/кнопка `key` зажата. Неизвестное имя -> False."""
    vk = _vk(key)
    if vk is None:
        return False
    return bool(_user32.GetAsyncKeyState(vk) & 0x8000)
