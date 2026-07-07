from __future__ import annotations

from pathlib import Path


def train(data_yaml: str, epochs: int, out_dir: str) -> str:
    from ultralytics import YOLO

    model = YOLO("yolov8n.pt")
    result = model.train(data=data_yaml, epochs=epochs, project=out_dir)
    save_dir = Path(getattr(result, "save_dir", out_dir))
    return str(save_dir / "weights" / "best.pt")
