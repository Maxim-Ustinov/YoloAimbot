"""Send a visible stream of Logitech virtual mouse movement.

Use this to check whether a focused game receives Logitech virtual mouse input.
Run it, immediately focus the game window, and watch whether the camera turns.
"""

from __future__ import annotations

import argparse
import time

from src.aim.logitech_mouse import LogitechMouse


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dx", type=int, default=20)
    parser.add_argument("--dy", type=int, default=0)
    parser.add_argument("--seconds", type=float, default=2.0)
    parser.add_argument("--hz", type=float, default=120.0)
    parser.add_argument("--warmup", type=float, default=2.0)
    args = parser.parse_args()

    print(f"focus the game now; starting in {args.warmup:.1f}s")
    time.sleep(max(0.0, args.warmup))

    interval = 1.0 / max(1.0, args.hz)
    deadline = time.perf_counter() + max(0.0, args.seconds)
    sent = failed = 0

    with LogitechMouse() as mouse:
        print(f"backend={mouse.open_mode}, dx={args.dx}, dy={args.dy}, seconds={args.seconds}, hz={args.hz}")
        while time.perf_counter() < deadline:
            if mouse.move_relative(args.dx, args.dy):
                sent += 1
            else:
                failed += 1
                print(f"move failed: error={mouse.last_error}")
            time.sleep(interval)

    print(f"done: sent={sent}, failed={failed}")


if __name__ == "__main__":
    main()
