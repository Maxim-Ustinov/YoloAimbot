"""Capture one live detection window and save YOLO diagnostics.

Run while AssaultCube is visible and the crosshair is on/near a player:
    python -m scripts.debug_live_detection

The script does not move the mouse. It only saves raw and annotated frames.
"""

from __future__ import annotations

import json
import time
from dataclasses import fields
from pathlib import Path

import cv2

from src.aim import Activation, AimConfig, AimMode, AimTarget, MouseBackend
from src.aim.controller import AimController
from src.aim.targeting import aim_point, select_target_with_debug
from src.capture import ScreenCapture
from src.detect import Detector

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "aim_config.json"
OUT_DIR = ROOT / "debug"


def load_config() -> AimConfig:
    if not CONFIG.exists():
        return AimConfig()
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    field_names = {field.name for field in fields(AimConfig)}
    data = {key: value for key, value in data.items() if key in field_names}
    if "target" in data:
        data["target"] = AimTarget(data["target"])
    if "activation" in data:
        data["activation"] = Activation(data["activation"])
    if "mode" in data:
        data["mode"] = AimMode(data["mode"])
    if "mouse_backend" in data:
        data["mouse_backend"] = MouseBackend(data["mouse_backend"])
    return AimConfig(**data)


def draw_box(frame, box, color, label: str) -> None:
    x1, y1, x2, y2 = map(int, (box.x1, box.y1, box.x2, box.y2))
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    cv2.putText(
        frame,
        label,
        (x1, max(14, y1 - 5)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        color,
        1,
        cv2.LINE_AA,
    )


def main() -> None:
    cfg = load_config()
    region = AimController(cfg)._capture_region()
    capture = ScreenCapture(region=region, target_fps=int(cfg.capture_fps))
    capture.start()
    try:
        time.sleep(0.25)
        frame = capture.latest_frame(timeout=2.0)
    finally:
        capture.close()

    if frame is None:
        raise RuntimeError("no frame captured")

    detector = Detector(
        weights=cfg.detector_model,
        conf=cfg.detector_conf,
        imgsz=max(320, int(round(cfg.detector_imgsz / 32) * 32)),
    )
    enemies, teammates = detector.detect(frame)
    h, w = frame.shape[:2]
    selection = select_target_with_debug(enemies, teammates, w, h, cfg)

    OUT_DIR.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    raw_path = OUT_DIR / f"live_raw_{stamp}.jpg"
    pred_path = OUT_DIR / f"live_pred_{stamp}.jpg"

    annotated = frame.copy()
    cv2.drawMarker(annotated, (w // 2, h // 2), (255, 255, 255), cv2.MARKER_CROSS, 28, 1)
    half_w = int(cfg.area_width_pct / 100.0 * w / 2)
    half_h = int(cfg.area_height_pct / 100.0 * h / 2)
    cv2.rectangle(
        annotated,
        (w // 2 - half_w, h // 2 - half_h),
        (w // 2 + half_w, h // 2 + half_h),
        (255, 255, 0),
        1,
    )

    for enemy in enemies:
        draw_box(annotated, enemy.body, (0, 0, 255), f"enemy {enemy.confidence:.2f}")
        px, py = map(int, aim_point(enemy, cfg))
        cv2.circle(annotated, (px, py), 4, (0, 255, 255), -1)
    for mate in teammates:
        draw_box(annotated, mate.body, (255, 0, 0), f"mate {mate.confidence:.2f}")

    cv2.imwrite(str(raw_path), frame)
    cv2.imwrite(str(pred_path), annotated)

    print(f"model: {detector.weights}")
    print(f"region: {region or 'full'} frame={w}x{h}")
    print(f"conf={cfg.detector_conf} imgsz={cfg.detector_imgsz}")
    print(
        "detections: "
        f"enemy={selection.enemies}, mate={selection.teammates}, "
        f"candidate={selection.candidates}, zone_skip={selection.outside_zone}, "
        f"mate_skip={selection.covered_by_teammate}, target={selection.target is not None}"
    )
    print(f"saved raw: {raw_path}")
    print(f"saved pred: {pred_path}")


if __name__ == "__main__":
    main()
