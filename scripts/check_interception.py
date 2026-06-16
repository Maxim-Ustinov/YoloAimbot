"""Быстрая диагностика Interception без движения мыши."""

import argparse
from pathlib import Path

from src.aim.interception_mouse import (
    INTERCEPTION_DLL,
    InterceptionMouse,
    device_path_for_mouse,
    is_process_elevated,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Check Interception context creation")
    parser.add_argument("--dll", type=Path, default=INTERCEPTION_DLL, help="path to interception.dll")
    parser.add_argument("--mouse-index", type=int, default=1)
    args = parser.parse_args()

    print("elevated:", is_process_elevated())
    print("dll:", args.dll)
    print("dll exists:", args.dll.exists())
    print("device:", device_path_for_mouse(args.mouse_index))
    with InterceptionMouse(mouse_index=args.mouse_index, dll_path=args.dll) as mouse:
        print("interception mouse device: ok")
        print("open mode:", mouse.open_mode)


if __name__ == "__main__":
    main()
