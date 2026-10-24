"""Model-free person detection: warm blobs against cold water, on a frame of degrees C.

A swimmer's head reads far warmer than lake water, so a temperature threshold finds
candidates without trained weights; TemporalPersistenceFilter drops one-frame glints.
It cannot tell a person from another warm object (a dog, a sunlit dock).
"""

from __future__ import annotations

from datetime import datetime, timezone

import cv2
import numpy as np

from app.models import Detection, Source


class HotSpotDetector:
    def __init__(self, min_c: float = 24.0, margin_c: float = 5.0, min_pixels: int = 4,
                 source: Source = "real") -> None:
        self.min_c = min_c          # absolute floor: never call anything colder a person
        self.margin_c = margin_c    # and it must stand this far above the scene's median
        self.min_pixels = min_pixels
        self.source = source

    def detect(self, temps: np.ndarray, frame_idx: int) -> list[Detection]:
        if temps.ndim != 2:
            raise ValueError("hot-spot detector expects a 2-D temperature frame")
        threshold = max(self.min_c, float(np.median(temps)) + self.margin_c)
        count, _, stats, _ = cv2.connectedComponentsWithStats((temps >= threshold).astype(np.uint8), connectivity=8)
        detections = []
        for x, y, w, h, area in stats[1:count]:
            if area < self.min_pixels:
                continue
            peak = float(temps[y:y + h, x:x + w].max())
            detections.append(Detection(
                frame_idx=frame_idx,
                bbox=(float(x), float(y), float(w), float(h)),
                # 0.5 at the threshold, 1.0 at 10 C above it.
                confidence=max(0.0, min(1.0, 0.5 + (peak - threshold) / 20.0)),
                timestamp=datetime.now(timezone.utc),
                source=self.source,
            ))
        return detections
