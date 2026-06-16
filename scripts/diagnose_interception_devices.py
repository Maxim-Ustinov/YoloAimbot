"""Показать доступность Win32 device paths Interception: \\\\.\\interception00..19."""

import ctypes

from src.aim.interception_mouse import (
    FILE_SHARE_READ,
    FILE_SHARE_WRITE,
    GENERIC_READ,
    GENERIC_WRITE,
    INVALID_HANDLE_VALUE,
    OPEN_EXISTING,
    is_process_elevated,
)


def main() -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = (
        ctypes.c_wchar_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_void_p,
    )
    kernel32.CreateFileW.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
    kernel32.CloseHandle.restype = ctypes.c_int

    print("elevated:", is_process_elevated())
    attempts = [
        ("read/exclusive", GENERIC_READ, 0),
        ("read/shared", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE),
        ("write/shared", GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE),
        ("none/shared", 0, FILE_SHARE_READ | FILE_SHARE_WRITE),
        ("readwrite/shared", GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE),
    ]
    for i in range(20):
        path = f"\\\\.\\interception{i:02d}"
        errors = []
        for mode, access, share in attempts:
            ctypes.set_last_error(0)
            handle = kernel32.CreateFileW(
                path,
                access,
                share,
                None,
                OPEN_EXISTING,
                0,
                None,
            )
            if handle != INVALID_HANDLE_VALUE:
                print(f"{path}: ok ({mode})")
                kernel32.CloseHandle(handle)
                break
            errors.append(f"{mode}={ctypes.get_last_error()}")
        else:
            print(f"{path}: failed ({', '.join(errors)})")


if __name__ == "__main__":
    main()
