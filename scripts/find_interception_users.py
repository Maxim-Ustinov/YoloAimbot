"""Find likely processes that keep Interception devices busy.

Run from an elevated PowerShell:
    python -m scripts.find_interception_users

If Sysinternals handle64.exe is available in C:\\AI or PATH, the script also
searches real kernel handles for interception device objects.
"""

from __future__ import annotations

import ctypes
import csv
import os
import shutil
import subprocess
from pathlib import Path


SUSPECT_NAMES = [
    "python.exe",
    "pythonw.exe",
    "identify.exe",
    "hardwareid.exe",
    "mathpointer.exe",
    "axes.exe",
    "cadstop.exe",
    "caps2esc.exe",
    "x2y.exe",
]


def is_elevated() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def run(args: list[str]) -> str:
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="oem",
            errors="replace",
            timeout=20,
        )
    except FileNotFoundError:
        return f"not found: {args[0]}"
    except subprocess.TimeoutExpired:
        return f"timeout: {' '.join(args)}"
    output = (completed.stdout or "") + (completed.stderr or "")
    return output.strip() or f"exit={completed.returncode}, no output"


def tasklist_image_rows(name: str, exclude_pids: set[int]) -> list[list[str]]:
    output = run(["tasklist", "/fi", f"imagename eq {name}", "/fo", "csv", "/nh", "/v"])
    if "INFO:" in output or "Информация:" in output:
        return []
    rows = []
    for row in csv.reader(output.splitlines()):
        if len(row) < 2:
            continue
        try:
            pid = int(row[1])
        except ValueError:
            continue
        if pid not in exclude_pids:
            rows.append(row)
    return rows


def format_tasklist_rows(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    lines = ["ImageName | PID | Session | Memory | Status | User | WindowTitle"]
    for row in rows:
        image = row[0] if len(row) > 0 else ""
        pid = row[1] if len(row) > 1 else ""
        session = row[2] if len(row) > 2 else ""
        memory = row[4] if len(row) > 4 else ""
        status = row[5] if len(row) > 5 else ""
        user = row[6] if len(row) > 6 else ""
        title = row[8] if len(row) > 8 else ""
        lines.append(f"{image} | {pid} | {session} | {memory} | {status} | {user} | {title}")
    return "\n".join(lines)


def process_command_line(pid: str) -> str:
    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        f"(Get-CimInstance Win32_Process -Filter \"ProcessId={pid}\").CommandLine",
    ]
    output = run(command)
    return output.replace("\r", " ").replace("\n", " ").strip()


def find_handle_exe() -> str | None:
    candidates = [
        Path("handle64.exe"),
        Path("handle.exe"),
        Path("tools") / "handle64.exe",
        Path("tools") / "handle.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return shutil.which("handle64.exe") or shutil.which("handle.exe")


def main() -> None:
    print("elevated:", is_elevated())
    current_pid = os.getpid()
    parent_pid = os.getppid()
    excluded_pids = {current_pid, parent_pid}
    print("self pid:", current_pid)
    print("parent pid:", parent_pid)

    print("\n[tasklist: loaded interception.dll]")
    print(run(["tasklist", "/m", "interception.dll"]))

    print("\n[tasklist: common suspects]")
    for name in SUSPECT_NAMES:
        rows = tasklist_image_rows(name, excluded_pids)
        if rows:
            print(f"\n{name}")
            print(format_tasklist_rows(rows))
            for row in rows:
                if len(row) > 1:
                    print(f"cmdline[{row[1]}]: {process_command_line(row[1])}")

    handle_exe = find_handle_exe()
    print("\n[handle.exe: kernel handles]")
    if handle_exe is None:
        print("handle64.exe not found. Put Sysinternals handle64.exe into C:\\AI or PATH.")
        return
    print(f"using: {handle_exe}")
    print(run([handle_exe, "-accepteula", "-nobanner", "interception"]))


if __name__ == "__main__":
    main()
