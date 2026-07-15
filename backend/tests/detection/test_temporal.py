from datetime import datetime, timezone

from app.detection.temporal import TemporalPersistenceFilter
from app.models import Detection


def mk_det(frame_idx: int, bbox=(10.0, 10.0, 5.0, 5.0)) -> Detection:
    return Detection(frame_idx, bbox, 0.9, datetime.now(timezone.utc), source="simulated")


def test_single_frame_blip_suppressed():
    f = TemporalPersistenceFilter(n_consecutive=3)
    assert f.update([mk_det(0)]) == []
    assert f.update([]) == []


def test_three_consecutive_emitted():
    f = TemporalPersistenceFilter(n_consecutive=3)
    f.update([mk_det(0)])
    f.update([mk_det(1, (11.0, 10.0, 5.0, 5.0))])
    out = f.update([mk_det(2, (10.5, 10.0, 5.0, 5.0))])
    assert len(out) == 1


def test_low_iou_breaks_streak():
    f = TemporalPersistenceFilter(n_consecutive=2, iou_thresh=0.3)
    f.update([mk_det(0)])
    assert f.update([mk_det(1, (80.0, 80.0, 5.0, 5.0))]) == []
