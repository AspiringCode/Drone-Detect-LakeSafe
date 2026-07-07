from __future__ import annotations

from pathlib import Path

from app.detection.dataset import load_clip
from app.detection.temporal import TemporalPersistenceFilter, _iou
from app.models import Detection


def _read_labels(path: Path, width: int, height: int) -> list[tuple[float, float, float, float]]:
    boxes: list[tuple[float, float, float, float]] = []
    if not path.exists():
        return boxes
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        _, cx, cy, w, h = [float(part) for part in line.split()]
        bw = w * width
        bh = h * height
        x = cx * width - bw / 2
        y = cy * height - bh / 2
        boxes.append((x, y, bw, bh))
    return boxes


def _has_match(detections: list[Detection], gt_boxes: list[tuple[float, float, float, float]]) -> bool:
    return any(_iou(det.bbox, gt) >= 0.3 for det in detections for gt in gt_boxes)


def evaluate(detector, dataset_dir: str, temporal: TemporalPersistenceFilter) -> dict[str, float | int]:
    """Evaluate fixture or staged clips; report dataset size for disclosure."""
    root = Path(dataset_dir)
    clips = sorted(
        (root / "clips").glob("*.npy"),
        key=lambda p: (0 if (root / "labels" / f"{p.stem}.txt").read_text(encoding="utf-8").strip() else 1, p.name),
    )
    positives = 0
    detected_positives = 0
    negatives = 0
    false_positives = 0

    for clip_path in clips:
        clip = load_clip(clip_path)
        height, width = clip.shape[1], clip.shape[2]
        labels = _read_labels(root / "labels" / f"{clip_path.stem}.txt", width, height)
        clip_detections: list[Detection] = []
        temporal._tracks = []
        for frame_idx, frame in enumerate(clip):
            clip_detections.extend(temporal.update(detector.detect(frame, frame_idx)))

        if labels:
            positives += 1
            if _has_match(clip_detections, labels):
                detected_positives += 1
        else:
            negatives += 1
            if clip_detections:
                false_positives += 1

    return {
        "detection_rate": detected_positives / positives if positives else 0.0,
        "false_positive_rate": false_positives / negatives if negatives else 0.0,
        "n_clips": len(clips),
    }
