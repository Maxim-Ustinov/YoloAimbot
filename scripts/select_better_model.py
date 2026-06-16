"""Select the better detector checkpoint by validation metrics."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from ultralytics import YOLO


def evaluate(weights: Path, data: Path, imgsz: int, batch: int, device: str, class_name: str) -> dict[str, float]:
    metrics = YOLO(str(weights)).val(
        data=str(data),
        imgsz=imgsz,
        batch=batch,
        device=device,
        verbose=False,
        plots=False,
        workers=0,
        half=device != "cpu",
    )

    result = {
        "overall_map50": float(metrics.results_dict["metrics/mAP50(B)"]),
        "overall_map": float(metrics.results_dict["metrics/mAP50-95(B)"]),
        "class_map50": 0.0,
        "class_map": 0.0,
        "class_precision": 0.0,
        "class_recall": 0.0,
    }
    for row_idx, cls_idx in enumerate(metrics.box.ap_class_index):
        name = metrics.names[int(cls_idx)]
        if name == class_name:
            result.update(
                {
                    "class_map50": float(metrics.box.ap50[row_idx]),
                    "class_map": float(metrics.box.ap[row_idx]),
                    "class_precision": float(metrics.box.p[row_idx]),
                    "class_recall": float(metrics.box.r[row_idx]),
                }
            )
            break
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy the better model to output")
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--class-name", default="EnemyHead")
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--batch", type=int, default=1)
    parser.add_argument("--device", default="0")
    args = parser.parse_args()

    for path in (args.baseline, args.candidate, args.data):
        if not path.exists():
            raise FileNotFoundError(path)

    baseline = evaluate(args.baseline, args.data, args.imgsz, args.batch, args.device, args.class_name)
    candidate = evaluate(args.candidate, args.data, args.imgsz, args.batch, args.device, args.class_name)

    baseline_score = (baseline["class_map50"], baseline["class_map"], baseline["overall_map50"])
    candidate_score = (candidate["class_map50"], candidate["class_map"], candidate["overall_map50"])
    selected = args.candidate if candidate_score >= baseline_score else args.baseline
    selected_metrics = candidate if selected == args.candidate else baseline

    shutil.copy2(selected, args.output)

    print(f"baseline: {args.baseline}")
    print(f"  {baseline}")
    print(f"candidate: {args.candidate}")
    print(f"  {candidate}")
    print(f"selected: {selected}")
    print(f"selected metrics: {selected_metrics}")
    print(f"output: {args.output}")


if __name__ == "__main__":
    main()
