"""Try a tiny write to the Logitech Gaming Virtual Mouse HID path.

This is intentionally conservative: by default it sends a very small square
using likely 6-byte mouse input reports. If the HID stack rejects WriteFile, the
script reports the Windows error and exits.
"""

from __future__ import annotations

import argparse
import ctypes
import time
from ctypes import wintypes

from scripts.probe_logitech_virtual_hid import (
    FILE_ATTRIBUTE_NORMAL,
    FILE_SHARE_READ,
    FILE_SHARE_WRITE,
    GENERIC_WRITE,
    INVALID_HANDLE_VALUE,
    OPEN_EXISTING,
    enum_hid_paths,
)

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

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
kernel32.WriteFile.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.c_void_p,
]
kernel32.WriteFile.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL


def find_mouse_path() -> str:
    candidates = [
        p
        for p in enum_hid_paths()
        if "vid_046d&pid_c231" in p.lower() and "mi_" not in p.lower()
    ]
    if not candidates:
        raise RuntimeError("Logitech virtual mouse HID path was not found")
    # Prefer the old LGS device that is currently OK on this machine.
    return candidates[0]


def open_mouse(path: str) -> wintypes.HANDLE:
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


def write_report(handle: wintypes.HANDLE, data: bytes) -> None:
    written = wintypes.DWORD()
    buffer = ctypes.create_string_buffer(data)
    ok = kernel32.WriteFile(handle, buffer, len(data), ctypes.byref(written), None)
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    if written.value != len(data):
        raise RuntimeError(f"short write: {written.value}/{len(data)}")


def report_6(dx: int, dy: int, buttons: int = 0, wheel: int = 0) -> bytes:
    dx = max(-32768, min(32767, int(dx)))
    dy = max(-32768, min(32767, int(dy)))
    wheel = max(-128, min(127, int(wheel)))
    return bytes([buttons & 0xFF]) + dx.to_bytes(2, "little", signed=True) + dy.to_bytes(2, "little", signed=True) + bytes([wheel & 0xFF])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", type=int, default=25)
    parser.add_argument("--delay", type=float, default=0.05)
    parser.add_argument("--path", default=None)
    args = parser.parse_args()

    path = args.path or find_mouse_path()
    print(f"path: {path}")
    handle = open_mouse(path)
    try:
        # A tiny square: right, down, left, up.
        moves = [(args.step, 0), (0, args.step), (-args.step, 0), (0, -args.step)]
        for dx, dy in moves:
            data = report_6(dx, dy)
            print(f"write {list(data)}")
            write_report(handle, data)
            time.sleep(args.delay)
        print("write completed")
    finally:
        kernel32.CloseHandle(handle)


if __name__ == "__main__":
    main()
