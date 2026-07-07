from __future__ import annotations

from app.models import Detection


def _iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ax2, ay2 = ax + aw, ay + ah
    bx2, by2 = bx + bw, by + bh
    inter_w = max(0.0, min(ax2, bx2) - max(ax, bx))
    inter_h = max(0.0, min(ay2, by2) - max(ay, by))
    inter = inter_w * inter_h
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


class TemporalPersistenceFilter:
    def __init__(self, n_consecutive: int = 3, iou_thresh: float = 0.3) -> None:
        self.n_consecutive = n_consecutive
        self.iou_thresh = iou_thresh
        self._tracks: list[tuple[Detection, int]] = []

    def update(self, frame_detections: list[Detection]) -> list[Detection]:
        if not frame_detections:
            self._tracks = []
            return []

        new_tracks: list[tuple[Detection, int]] = []
        emitted: list[Detection] = []
        used: set[int] = set()

        for det in frame_detections:
            best_idx = None
            best_iou = 0.0
            for idx, (prev, _) in enumerate(self._tracks):
                score = _iou(prev.bbox, det.bbox)
                if idx not in used and score > best_iou:
                    best_idx = idx
                    best_iou = score
            streak = 1
            if best_idx is not None and best_iou >= self.iou_thresh:
                streak = self._tracks[best_idx][1] + 1
                used.add(best_idx)
            new_tracks.append((det, streak))
            if streak >= self.n_consecutive:
                emitted.append(det)

        self._tracks = new_tracks
        return emitted
