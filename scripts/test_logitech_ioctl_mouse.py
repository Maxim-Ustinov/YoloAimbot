"""Test Logitech LGS/G HUB virtual mouse IOCTL injection.

This uses the same public constants/structure layout as IbInputSimulator's
Logitech backend:
  - old LGS mouse report: 5 bytes, IOCTL 0x2A2010
  - new G HUB mouse report: 8 bytes, IOCTL 0x2A2010

It draws a tiny square if the driver accepts the IOCTL.
"""

from __future__ import annotations

import argparse
import ctypes
import time
from ctypes import wintypes

from scripts.probe_logitech_virtual_hid import (
    DIGCF_DEVICEINTERFACE,
    DIGCF_PRESENT,
    ERROR_INSUFFICIENT_BUFFER,
    ERROR_NO_MORE_ITEMS,
    FILE_ATTRIBUTE_NORMAL,
    FILE_SHARE_READ,
    FILE_SHARE_WRITE,
    GENERIC_WRITE,
    GUID,
    INVALID_HANDLE_VALUE,
    OPEN_EXISTING,
    SP_DEVICE_INTERFACE_DATA,
    SP_DEVINFO_DATA,
)

IOCTL_BUSENUM_PLAY_MOUSEMOVE = 0x2A2010

GUIDS = {
    "Logitech": [
        GUID(0xDF31F106, 0xD870, 0x453D, (ctypes.c_ubyte * 8)(0x8F, 0xA1, 0xEC, 0x8A, 0xB4, 0x3F, 0xA1, 0xD2)),
        GUID(0x5BADA891, 0x842B, 0x4296, (ctypes.c_ubyte * 8)(0xA4, 0x96, 0x68, 0xAE, 0x93, 0x1A, 0xA1, 0x6C)),
    ],
    "LogitechGHubNew": [
        GUID(0x1ABC05C0, 0xC378, 0x41B9, (ctypes.c_ubyte * 8)(0x9C, 0xEF, 0xDF, 0x1A, 0xBA, 0x82, 0xB0, 0x15)),
        GUID(0xDFBEDCDB, 0x2148, 0x416D, (ctypes.c_ubyte * 8)(0x9E, 0x4D, 0xCE, 0xCC, 0x24, 0x24, 0x12, 0x8C)),
    ],
}

setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
setupapi.SetupDiGetClassDevsW.restype = wintypes.HANDLE
setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(SP_DEVINFO_DATA),
    ctypes.POINTER(GUID),
    wintypes.DWORD,
    ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
]
setupapi.SetupDiEnumDeviceInterfaces.restype = wintypes.BOOL
setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(SP_DEVICE_INTERFACE_DATA),
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.POINTER(SP_DEVINFO_DATA),
]
setupapi.SetupDiGetDeviceInterfaceDetailW.restype = wintypes.BOOL
setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]
setupapi.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL

kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.HANDLE,
]
kernel32.CreateFileW.restype = wintypes.HANDLE
kernel32.DeviceIoControl.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.c_void_p,
]
kernel32.DeviceIoControl.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL


def enum_interface_paths(guid: GUID) -> list[str]:
    info = setupapi.SetupDiGetClassDevsW(
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
            ok = setupapi.SetupDiEnumDeviceInterfaces(info, None, ctypes.byref(guid), index, ctypes.byref(iface))
            if not ok:
                err = ctypes.get_last_error()
                if err == ERROR_NO_MORE_ITEMS:
                    break
                raise ctypes.WinError(err)

            required = wintypes.DWORD()
            setupapi.SetupDiGetDeviceInterfaceDetailW(info, ctypes.byref(iface), None, 0, ctypes.byref(required), None)
            if ctypes.get_last_error() != ERROR_INSUFFICIENT_BUFFER:
                raise ctypes.WinError(ctypes.get_last_error())

            detail = ctypes.create_string_buffer(required.value)
            ctypes.cast(detail, ctypes.POINTER(wintypes.DWORD))[0] = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
            devinfo = SP_DEVINFO_DATA()
            devinfo.cbSize = ctypes.sizeof(devinfo)
            ok = setupapi.SetupDiGetDeviceInterfaceDetailW(
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
        setupapi.SetupDiDestroyDeviceInfoList(info)
    return paths


def find_paths(kind: str) -> list[str]:
    paths: list[str] = []
    for guid in GUIDS[kind]:
        paths.extend(enum_interface_paths(guid))
    return [p for p in paths if "root#system#" in p.lower()]


def open_device(path: str) -> wintypes.HANDLE:
    handle = kernel32.CreateFileW(
        path,
        GENERIC_WRITE,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL,
        None,
    )
    if handle == INVALID_HANDLE_VALUE:
        raise ctypes.WinError(ctypes.get_last_error())
    return handle


def report_lgs(dx: int, dy: int, buttons: int = 0, wheel: int = 0) -> bytes:
    dx = max(-127, min(127, int(dx)))
    dy = max(-127, min(127, int(dy)))
    wheel = max(-127, min(127, int(wheel)))
    return bytes([buttons & 0xFF, dx & 0xFF, dy & 0xFF, wheel & 0xFF, 0])


def report_ghub_new(dx: int, dy: int, buttons: int = 0, wheel: int = 0) -> bytes:
    dx = max(-32768, min(32767, int(dx)))
    dy = max(-32768, min(32767, int(dy)))
    wheel = max(-127, min(127, int(wheel)))
    # C++ layout: byte button, 1 byte padding, int16 x, int16 y, byte wheel, byte unknown.
    return bytes([buttons & 0xFF, 0]) + dx.to_bytes(2, "little", signed=True) + dy.to_bytes(2, "little", signed=True) + bytes([wheel & 0xFF, 0])


def send_report(handle: wintypes.HANDLE, report: bytes) -> None:
    returned = wintypes.DWORD()
    buf = ctypes.create_string_buffer(report)
    ctypes.set_last_error(0)
    ok = kernel32.DeviceIoControl(
        handle,
        IOCTL_BUSENUM_PLAY_MOUSEMOVE,
        buf,
        len(report),
        None,
        0,
        ctypes.byref(returned),
        None,
    )
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=["Logitech", "LogitechGHubNew"], default="Logitech")
    parser.add_argument("--step", type=int, default=30)
    parser.add_argument("--delay", type=float, default=0.06)
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()

    paths = find_paths(args.kind)
    print(f"{args.kind} control paths: {len(paths)}")
    for path in paths:
        print(f"  {path}")
    if args.list:
        return
    if not paths:
        raise RuntimeError(f"No {args.kind} control path found")

    report_fn = report_lgs if args.kind == "Logitech" else report_ghub_new
    handle = open_device(paths[0])
    try:
        for dx, dy in ((args.step, 0), (0, args.step), (-args.step, 0), (0, -args.step)):
            report = report_fn(dx, dy)
            print(f"ioctl {list(report)}")
            send_report(handle, report)
            time.sleep(args.delay)
        print("ioctl completed")
    finally:
        kernel32.CloseHandle(handle)


if __name__ == "__main__":
    main()
