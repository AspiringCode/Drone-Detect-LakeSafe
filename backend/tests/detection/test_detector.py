from app.detection.dataset import SyntheticThermalClip
from app.detection.detector import ThermalDetector


class FakeBox:
    xyxy = [[10.0, 12.0, 18.0, 22.0]]
    conf = [0.82]


class FakeResult:
    boxes = [FakeBox()]


def test_detect_returns_detections_with_source(monkeypatch):
    det = ThermalDetector(model_path=None, source="simulated", model=object())

    def fake_predict(frame):
        assert frame.ndim == 3
        assert frame.shape[2] == 3
        return [FakeResult()]

    monkeypatch.setattr(det, "_predict", fake_predict)
    results = det.detect(SyntheticThermalClip(1, with_target=True)[0], frame_idx=0)

    assert len(results) == 1
    assert all(0.0 <= r.confidence <= 1.0 for r in results)
    assert all(r.source == "simulated" for r in results)
    assert results[0].bbox == (10.0, 12.0, 8.0, 10.0)
