"""Отправка относительного движения мыши через Interception driver.

Это отдельный экспериментальный backend: Interception работает через системный
filter driver и отправляет события ближе к уровню физического устройства, чем
обычный WinAPI SendInput.
"""

from __future__ import annotations

import ctypes
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INTERCEPTION_DLL = PROJECT_ROOT / "Interception" / "library" / "x64" / "interception.dll"

INTERCEPTION_MAX_KEYBOARD = 10
INTERCEPTION_MOUSE_MOVE_RELATIVE = 0x000
# Флаги кнопок в поле state stroke'а (совпадают с RI_MOUSE_* для direct-пути).
INTERCEPTION_MOUSE_LEFT_DOWN = 0x001
INTERCEPTION_MOUSE_LEFT_UP = 0x002

FILE_DEVICE_UNKNOWN = 0x00000022
METHOD_BUFFERED = 0
FILE_ANY_ACCESS = 0
IOCTL_WRITE = (FILE_DEVICE_UNKNOWN << 16) | (FILE_ANY_ACCESS << 14) | (0x820 << 2) | METHOD_BUFFERED

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


def is_process_elevated() -> bool:
    """True, если текущий Python запущен с правами администратора."""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


class InterceptionMouseStroke(ctypes.Structure):
    _fields_ = [
        ("state", ctypes.c_ushort),
        ("flags", ctypes.c_ushort),
        ("rolling", ctypes.c_short),
        ("x", ctypes.c_int),
        ("y", ctypes.c_int),
        ("information", ctypes.c_uint),
    ]


class _MouseInputData(ctypes.Structure):
    _fields_ = [
        ("UnitId", ctypes.c_ushort),
        ("Flags", ctypes.c_ushort),
        ("ButtonFlags", ctypes.c_ushort),
        ("ButtonData", ctypes.c_ushort),
        ("RawButtons", ctypes.c_ulong),
        ("LastX", ctypes.c_long),
        ("LastY", ctypes.c_long),
        ("ExtraInformation", ctypes.c_ulong),
    ]


def mouse_device(mouse_index: int) -> int:
    """Interception device id по номеру из identify.exe: INTERCEPTION_MOUSE(index)."""
    return INTERCEPTION_MAX_KEYBOARD + mouse_index + 1


def device_path_for_mouse(mouse_index: int) -> str:
    """Win32 device path for INTERCEPTION_MOUSE(index)."""
    return f"\\\\.\\interception{mouse_device(mouse_index) - 1:02d}"


class InterceptionMouse:
    def __init__(self, mouse_index: int = 1, dll_path: str | Path = INTERCEPTION_DLL):
        dll_path = Path(dll_path)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32.CreateFileW.argtypes = (
            ctypes.c_wchar_p,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_ulong,
            ctypes.c_void_p,
        )
        self._kernel32.CreateFileW.restype = ctypes.c_void_p
        self._kernel32.DeviceIoControl.argtypes = (
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong),
            ctypes.c_void_p,
        )
        self._kernel32.DeviceIoControl.restype = ctypes.c_int
        self._kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
        self._kernel32.CloseHandle.restype = ctypes.c_int

        self._device_path = device_path_for_mouse(mouse_index)
        self._handle = INVALID_HANDLE_VALUE
        self._api_dll = None
        self._api_context = None
        self._api_device = mouse_device(mouse_index)
        self.open_mode = ""
        self.last_error = 0
        # На этой системе прямое открытие device path работает стабильнее, чем
        # interception_create_context: неудачный API init может оставить драйвер
        # в состоянии, где последующий direct-open в том же процессе получает
        # ERROR_ACCESS_DENIED. Поэтому сначала direct, API — только fallback.
        direct_error = self._open_direct_device()
        if self._handle != INVALID_HANDLE_VALUE:
            return

        api_error = self._open_api_context(dll_path)
        if self._api_context:
            return

        raise RuntimeError(
            "Interception mouse init failed "
            f"(device={self._device_path}, direct_error={direct_error}, "
            f"api_error={api_error}, elevated={is_process_elevated()}). "
            "Проверь, что драйвер установлен, Windows перезагружена, "
            "а Interception не занят другой программой."
        )

    def _open_direct_device(self) -> int:
        error = 0
        attempts = [
            ("read/exclusive", GENERIC_READ, 0),
            ("read/shared", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE),
            ("write/shared", GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE),
            ("none/shared", 0, FILE_SHARE_READ | FILE_SHARE_WRITE),
            ("readwrite/shared", GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE),
        ]
        # 10 × 0.2с: хватает переждать занятость девайса, но init не блокирует
        # поток наводки на десятки секунд, если девайс реально недоступен.
        for _ in range(10):
            for mode, access, share in attempts:
                ctypes.set_last_error(0)
                self._handle = self._kernel32.CreateFileW(
                    self._device_path,
                    access,
                    share,
                    None,
                    OPEN_EXISTING,
                    0,
                    None,
                )
                if self._handle != INVALID_HANDLE_VALUE:
                    self.open_mode = mode
                    break
                error = ctypes.get_last_error()
            if self._handle != INVALID_HANDLE_VALUE:
                break
            time.sleep(0.2)
        return error

    def _open_api_context(self, dll_path: Path) -> int:
        if not dll_path.exists():
            raise FileNotFoundError(f"Interception DLL not found: {dll_path}")

        self._api_dll = ctypes.CDLL(str(dll_path), use_last_error=True)
        self._api_dll.interception_create_context.argtypes = ()
        self._api_dll.interception_create_context.restype = ctypes.c_void_p
        self._api_dll.interception_destroy_context.argtypes = (ctypes.c_void_p,)
        self._api_dll.interception_destroy_context.restype = None
        self._api_dll.interception_send.argtypes = (
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_uint,
        )
        self._api_dll.interception_send.restype = ctypes.c_int

        error = 0
        for _ in range(10):
            self._api_context = self._api_dll.interception_create_context()
            if self._api_context:
                self.open_mode = f"api-context:{self._api_device}"
                break
            error = ctypes.get_last_error()
            time.sleep(0.2)
        return error

    def close(self) -> None:
        if self._api_context:
            self._api_dll.interception_destroy_context(self._api_context)
            self._api_context = None
        if self._handle != INVALID_HANDLE_VALUE:
            self._kernel32.CloseHandle(self._handle)
            self._handle = INVALID_HANDLE_VALUE

    def _send_stroke(self, button_state: int, dx: int, dy: int) -> int:
        """Один stroke в драйвер: движение (dx/dy) и/или кнопки (button_state)."""
        if self._api_context:
            stroke = InterceptionMouseStroke(
                state=button_state,
                flags=INTERCEPTION_MOUSE_MOVE_RELATIVE,
                rolling=0,
                x=int(dx),
                y=int(dy),
                information=0,
            )
            sent = int(
                self._api_dll.interception_send(
                    self._api_context,
                    self._api_device,
                    ctypes.byref(stroke),
                    1,
                )
            )
            self.last_error = 0 if sent else ctypes.get_last_error()
            return sent

        stroke = _MouseInputData(
            UnitId=0,
            Flags=INTERCEPTION_MOUSE_MOVE_RELATIVE,
            ButtonFlags=button_state,
            ButtonData=0,
            RawButtons=0,
            LastX=int(dx),
            LastY=int(dy),
            ExtraInformation=0,
        )
        bytes_returned = ctypes.c_ulong(0)
        ok = self._kernel32.DeviceIoControl(
            self._handle,
            IOCTL_WRITE,
            ctypes.byref(stroke),
            ctypes.sizeof(stroke),
            None,
            0,
            ctypes.byref(bytes_returned),
            None,
        )
        self.last_error = 0 if ok else ctypes.get_last_error()
        return 1 if ok else 0

    def move_relative(self, dx: int, dy: int) -> int:
        if dx == 0 and dy == 0:
            return 0
        return self._send_stroke(0, dx, dy)

    def click_left(self, delay: float = 0.01) -> bool:
        """Клик ЛКМ через драйвер: нажатие, короткая пауза, отпускание."""
        if not self._send_stroke(INTERCEPTION_MOUSE_LEFT_DOWN, 0, 0):
            return False
        time.sleep(delay)
        return bool(self._send_stroke(INTERCEPTION_MOUSE_LEFT_UP, 0, 0))

    def __enter__(self) -> "InterceptionMouse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()
