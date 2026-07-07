from datetime import datetime

from app.detection.dataset import make_fixture_dataset
from app.detection.evaluate import evaluate
from app.detection.temporal import TemporalPersistenceFilter
from app.models import Detection


class StubDetector:
    def __init__(self) -> None:
        self.calls = 0

    def detect(self, frame, frame_idx: int):
        self.calls += 1
        if self.calls <= 8:
            return [Detection(frame_idx, (54.0, 47.0, 10.0, 10.0), 0.9, datetime.utcnow(), "simulated")]
        if self.calls == 11:
            return [Detection(frame_idx, (5.0, 5.0, 8.0, 8.0), 0.8, datetime.utcnow(), "simulated")]
        return []


def test_evaluate_computes_rates_against_ground_truth(tmp_path):
    dataset_dir = make_fixture_dataset(tmp_path, n_positive=10, n_negative=1)
    metrics = evaluate(StubDetector(), dataset_dir=str(dataset_dir), temporal=TemporalPersistenceFilter(1))

    assert metrics["n_clips"] == 11
    assert abs(metrics["detection_rate"] - 0.8) < 1e-6
    assert metrics["false_positive_rate"] > 0
    assert 0.0 <= metrics["false_positive_rate"] <= 1.0
