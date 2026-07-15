from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from app.models import Detection, Source


class ThermalDetector:
    def __init__(
        self,
        model_path: str | None = None,
        source: Source = "simulated",
        model: object | None = None,
    ) -> None:
        self.source = source
        self._model = model if model is not None else self._load_model(model_path)

    def _load_model(self, model_path: str | None) -> object:
        from ultralytics import YOLO

        return YOLO(model_path or "yolov8n.pt")

    def _prepare_frame(self, frame: np.ndarray) -> np.ndarray:
        if frame.ndim != 2:
            raise ValueError("thermal detector expects a single-channel frame array")
        return np.repeat(frame[:, :, None], 3, axis=2)

    def _predict(self, frame: np.ndarray):
        return self._model.predict(frame, verbose=False)

    def detect(self, frame: np.ndarray, frame_idx: int) -> list[Detection]:
        prepared = self._prepare_frame(frame)
        results = self._predict(prepared)
        detections: list[Detection] = []
        for result in results:
            for box in getattr(result, "boxes", []):
                xyxy = np.asarray(getattr(box, "xyxy"))[0].astype(float)
                conf = float(np.asarray(getattr(box, "conf"))[0])
                x1, y1, x2, y2 = xyxy
                detections.append(
                    Detection(
                        frame_idx=frame_idx,
                        bbox=(float(x1), float(y1), float(x2 - x1), float(y2 - y1)),
                        confidence=max(0.0, min(1.0, conf)),
                        timestamp=datetime.now(timezone.utc),
                        source=self.source,
                    )
                )
        return detections
