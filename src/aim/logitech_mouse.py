"""Relative mouse movement through Logitech Gaming Software virtual HID.

This backend talks to the Logitech virtual bus control interface used by the
old LGS `LGVirHid`/`LGBusEnum` drivers. It does not use SendInput and does not
open the child HID mouse path directly.
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

DIGCF_PRESENT = 0x00000002
DIGCF_DEVICEINTERFACE = 0x00000010
ERROR_INSUFFICIENT_BUFFER = 122
ERROR_NO_MORE_ITEMS = 259

GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x00000080
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

IOCTL_BUSENUM_PLAY_MOUSEMOVE = 0x2A2010


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("InterfaceClassGuid", GUID),
        ("Flags", wintypes.DWORD),
        ("Reserved", ctypes.c_void_p),
    ]


class SP_DEVINFO_DATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("ClassGuid", GUID),
        ("DevInst", wintypes.DWORD),
        ("Reserved", ctypes.c_void_p),
    ]


LOGITECH_CONTROL_GUIDS = (
    GUID(0xDF31F106, 0xD870, 0x453D, (ctypes.c_ubyte * 8)(0x8F, 0xA1, 0xEC, 0x8A, 0xB4, 0x3F, 0xA1, 0xD2)),
    GUID(0x5BADA891, 0x842B, 0x4296, (ctypes.c_ubyte * 8)(0xA4, 0x96, 0x68, 0xAE, 0x93, 0x1A, 0xA1, 0x6C)),
)


class LogitechMouse:
    def __init__(self):
        self._setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._configure_apis()
        self._handle = INVALID_HANDLE_VALUE
        self._path = self._find_control_path()
        self.open_mode = "logitech"
        self.last_error = 0
        self._open()

    def _configure_apis(self) -> None:
        self._setupapi.SetupDiGetClassDevsW.argtypes = [
            ctypes.POINTER(GUID),
            wintypes.LPCWSTR,
            wintypes.HWND,
            wintypes.DWORD,
        ]
        self._setupapi.SetupDiGetClassDevsW.restype = wintypes.HANDLE
        self._setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(SP_DEVINFO_DATA),
            ctypes.POINTER(GUID),
            wintypes.DWORD,
            ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
        ]
        self._setupapi.SetupDiEnumDeviceInterfaces.restype = wintypes.BOOL
        self._setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(SP_DEVINFO_DATA),
        ]
        self._setupapi.SetupDiGetDeviceInterfaceDetailW.restype = wintypes.BOOL
        self._setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]
        self._setupapi.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL

        self._kernel32.CreateFileW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        self._kernel32.CreateFileW.restype = wintypes.HANDLE
        self._kernel32.DeviceIoControl.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            ctypes.c_void_p,
        ]
        self._kernel32.DeviceIoControl.restype = wintypes.BOOL
        self._kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self._kernel32.CloseHandle.restype = wintypes.BOOL

    def _enum_interface_paths(self, guid: GUID) -> list[str]:
        info = self._setupapi.SetupDiGetClassDevsW(
            ctypes.byref(guid),
            None,
            None,
            DIGCF_PRESENT | DIGCF_DEVICEINTERFACE,
        )
        if info == INVALID_HANDLE_VALUE:
            return []

        paths: list[str] = []
        try:
            index = 0
            while True:
                iface = SP_DEVICE_INTERFACE_DATA()
                iface.cbSize = ctypes.sizeof(iface)
                ctypes.set_last_error(0)
                ok = self._setupapi.SetupDiEnumDeviceInterfaces(
                    info,
                    None,
                    ctypes.byref(guid),
                    index,
                    ctypes.byref(iface),
                )
                if not ok:
                    error = ctypes.get_last_error()
                    if error == ERROR_NO_MORE_ITEMS:
                        break
                    raise ctypes.WinError(error)

                required = wintypes.DWORD()
                self._setupapi.SetupDiGetDeviceInterfaceDetailW(
                    info,
                    ctypes.byref(iface),
                    None,
                    0,
                    ctypes.byref(required),
                    None,
                )
                if ctypes.get_last_error() != ERROR_INSUFFICIENT_BUFFER:
                    raise ctypes.WinError(ctypes.get_last_error())

                detail = ctypes.create_string_buffer(required.value)
                ctypes.cast(detail, ctypes.POINTER(wintypes.DWORD))[0] = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
                devinfo = SP_DEVINFO_DATA()
                devinfo.cbSize = ctypes.sizeof(devinfo)
                ok = self._setupapi.SetupDiGetDeviceInterfaceDetailW(
                    info,
                    ctypes.byref(iface),
                    detail,
                    required,
                    None,
                    ctypes.byref(devinfo),
                )
                if not ok:
                    raise ctypes.WinError(ctypes.get_last_error())

                raw = detail.raw[ctypes.sizeof(wintypes.DWORD) :]
                path = raw.decode("utf-16-le", errors="ignore").split("\x00", 1)[0]
                paths.append(path)
                index += 1
        finally:
            self._setupapi.SetupDiDestroyDeviceInfoList(info)
        return paths

    def _find_control_path(self) -> str:
        for guid in LOGITECH_CONTROL_GUIDS:
            for path in self._enum_interface_paths(guid):
                if "root#system#" in path.lower():
                    return path
        raise RuntimeError(
            "Logitech virtual mouse control path not found. "
            "Check that LGBusEnum/LGVirHid are installed and Logitech Gaming Virtual Bus Enumerator is OK."
        )

    def _open(self) -> None:
        last_error = 0
        for _ in range(20):
            ctypes.set_last_error(0)
            self._handle = self._kernel32.CreateFileW(
                self._path,
                GENERIC_WRITE,
                FILE_SHARE_READ | FILE_SHARE_WRITE,
                None,
                OPEN_EXISTING,
                FILE_ATTRIBUTE_NORMAL,
                None,
            )
            if self._handle != INVALID_HANDLE_VALUE:
                return
            last_error = ctypes.get_last_error()
            time.sleep(0.1)
        raise RuntimeError(f"Logitech virtual mouse open failed (path={self._path}, error={last_error})")

    @staticmethod
    def _report(dx: int, dy: int) -> bytes:
        dx = max(-127, min(127, int(dx)))
        dy = max(-127, min(127, int(dy)))
        return bytes([0, dx & 0xFF, dy & 0xFF, 0, 0])

    def _send_report(self, report: bytes) -> bool:
        returned = wintypes.DWORD()
        buffer = ctypes.create_string_buffer(report)
        ctypes.set_last_error(0)
        ok = self._kernel32.DeviceIoControl(
            self._handle,
            IOCTL_BUSENUM_PLAY_MOUSEMOVE,
            buffer,
            len(report),
            None,
            0,
            ctypes.byref(returned),
            None,
        )
        self.last_error = 0 if ok else ctypes.get_last_error()
        return bool(ok)

    def move_relative(self, dx: int, dy: int) -> int:
        if dx == 0 and dy == 0:
            return 0
        remaining_x = int(dx)
        remaining_y = int(dy)
        sent = 0
        while remaining_x or remaining_y:
            step_x = max(-127, min(127, remaining_x))
            step_y = max(-127, min(127, remaining_y))
            if not self._send_report(self._report(step_x, step_y)):
                return 0
            remaining_x -= step_x
            remaining_y -= step_y
            sent += 1
        return sent

    def click_left(self, delay: float = 0.01) -> bool:
        """Клик ЛКМ: первый байт репорта — маска кнопок (бит 0 = левая)."""
        if not self._send_report(bytes([1, 0, 0, 0, 0])):
            return False
        time.sleep(delay)
        return bool(self._send_report(bytes([0, 0, 0, 0, 0])))

    def close(self) -> None:
        if self._handle != INVALID_HANDLE_VALUE:
            self._kernel32.CloseHandle(self._handle)
            self._handle = INVALID_HANDLE_VALUE

    def __enter__(self) -> "LogitechMouse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()
