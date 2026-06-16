"""Probe Logitech virtual HID devices.

This script is read-only except for harmless CreateFile open attempts. It does
not send any movement. The goal is to learn whether the Logitech virtual mouse
exposes a standard writable HID output report or only a private control channel.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes


DIGCF_PRESENT = 0x00000002
DIGCF_DEVICEINTERFACE = 0x00000010
ERROR_INSUFFICIENT_BUFFER = 122
ERROR_NO_MORE_ITEMS = 259

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x00000080
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

HIDP_STATUS_SUCCESS = 0x00110000


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


GUID_DEVINTERFACE_HID = GUID(
    0x4D1E55B2,
    0xF16F,
    0x11CF,
    (ctypes.c_ubyte * 8)(0x88, 0xCB, 0x00, 0x11, 0x11, 0x00, 0x00, 0x30),
)


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


class HIDD_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("Size", wintypes.ULONG),
        ("VendorID", wintypes.USHORT),
        ("ProductID", wintypes.USHORT),
        ("VersionNumber", wintypes.USHORT),
    ]


class HIDP_CAPS(ctypes.Structure):
    _fields_ = [
        ("Usage", wintypes.USHORT),
        ("UsagePage", wintypes.USHORT),
        ("InputReportByteLength", wintypes.USHORT),
        ("OutputReportByteLength", wintypes.USHORT),
        ("FeatureReportByteLength", wintypes.USHORT),
        ("Reserved", wintypes.USHORT * 17),
        ("NumberLinkCollectionNodes", wintypes.USHORT),
        ("NumberInputButtonCaps", wintypes.USHORT),
        ("NumberInputValueCaps", wintypes.USHORT),
        ("NumberInputDataIndices", wintypes.USHORT),
        ("NumberOutputButtonCaps", wintypes.USHORT),
        ("NumberOutputValueCaps", wintypes.USHORT),
        ("NumberOutputDataIndices", wintypes.USHORT),
        ("NumberFeatureButtonCaps", wintypes.USHORT),
        ("NumberFeatureValueCaps", wintypes.USHORT),
        ("NumberFeatureDataIndices", wintypes.USHORT),
    ]


setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
hid = ctypes.WinDLL("hid", use_last_error=True)

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
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL

hid.HidD_GetAttributes.argtypes = [wintypes.HANDLE, ctypes.POINTER(HIDD_ATTRIBUTES)]
hid.HidD_GetAttributes.restype = wintypes.BOOLEAN
hid.HidD_GetPreparsedData.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
hid.HidD_GetPreparsedData.restype = wintypes.BOOLEAN
hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
hid.HidD_FreePreparsedData.restype = wintypes.BOOLEAN
hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS)]
hid.HidP_GetCaps.restype = ctypes.c_long


def create_file(path: str, access: int, share: int) -> tuple[int | None, int]:
    ctypes.set_last_error(0)
    handle = kernel32.CreateFileW(path, access, share, None, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, None)
    if handle == INVALID_HANDLE_VALUE:
        return None, ctypes.get_last_error()
    return int(handle), 0


def close(handle: int | None) -> None:
    if handle is not None:
        kernel32.CloseHandle(wintypes.HANDLE(handle))


def get_hid_caps(path: str) -> tuple[str, str]:
    handle, error = create_file(path, 0, FILE_SHARE_READ | FILE_SHARE_WRITE)
    if handle is None:
        return f"open(no-access) failed err={error}", ""
    try:
        attrs = HIDD_ATTRIBUTES()
        attrs.Size = ctypes.sizeof(attrs)
        attr_text = "attrs unavailable"
        if hid.HidD_GetAttributes(wintypes.HANDLE(handle), ctypes.byref(attrs)):
            attr_text = (
                f"vid={attrs.VendorID:04x} pid={attrs.ProductID:04x} "
                f"version={attrs.VersionNumber:04x}"
            )

        preparsed = ctypes.c_void_p()
        if not hid.HidD_GetPreparsedData(wintypes.HANDLE(handle), ctypes.byref(preparsed)):
            return attr_text, "preparsed unavailable"
        try:
            caps = HIDP_CAPS()
            status = hid.HidP_GetCaps(preparsed, ctypes.byref(caps))
            if status != HIDP_STATUS_SUCCESS:
                return attr_text, f"HidP_GetCaps status=0x{status:x}"
            caps_text = (
                f"usage_page=0x{caps.UsagePage:04x} usage=0x{caps.Usage:04x} "
                f"in={caps.InputReportByteLength} out={caps.OutputReportByteLength} "
                f"feature={caps.FeatureReportByteLength} "
                f"out_buttons={caps.NumberOutputButtonCaps} out_values={caps.NumberOutputValueCaps}"
            )
            return attr_text, caps_text
        finally:
            hid.HidD_FreePreparsedData(preparsed)
    finally:
        close(handle)


def enum_hid_paths() -> list[str]:
    info = setupapi.SetupDiGetClassDevsW(
        ctypes.byref(GUID_DEVINTERFACE_HID),
        None,
        None,
        DIGCF_PRESENT | DIGCF_DEVICEINTERFACE,
    )
    if info == INVALID_HANDLE_VALUE:
        raise ctypes.WinError(ctypes.get_last_error())

    paths: list[str] = []
    try:
        index = 0
        while True:
            iface = SP_DEVICE_INTERFACE_DATA()
            iface.cbSize = ctypes.sizeof(iface)
            ctypes.set_last_error(0)
            ok = setupapi.SetupDiEnumDeviceInterfaces(
                info,
                None,
                ctypes.byref(GUID_DEVINTERFACE_HID),
                index,
                ctypes.byref(iface),
            )
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

            path_offset = ctypes.sizeof(wintypes.DWORD)
            raw = detail.raw[path_offset:]
            path = raw.decode("utf-16-le", errors="ignore").split("\x00", 1)[0]
            paths.append(path)
            index += 1
    finally:
        setupapi.SetupDiDestroyDeviceInfoList(info)
    return paths


def main() -> None:
    paths = [
        p
        for p in enum_hid_paths()
        if "vid_046d&pid_c231" in p.lower()
        or "vid_046d&pid_c232" in p.lower()
        or "logidevice" in p.lower()
        or "lghubdevice" in p.lower()
    ]
    print(f"matching HID interfaces: {len(paths)}")
    for path in paths:
        print("\n" + path)
        for label, access, share in (
            ("none/shared", 0, FILE_SHARE_READ | FILE_SHARE_WRITE),
            ("read/shared", GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE),
            ("write/shared", GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE),
            ("readwrite/shared", GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE),
        ):
            handle, error = create_file(path, access, share)
            if handle is None:
                print(f"  open {label}: error={error}")
            else:
                print(f"  open {label}: ok")
                close(handle)
        attrs, caps = get_hid_caps(path)
        print(f"  {attrs}")
        if caps:
            print(f"  {caps}")


if __name__ == "__main__":
    main()
