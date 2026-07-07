import numpy as np

from app.detection.dataset import SyntheticThermalClip, augment


def test_augment_returns_distinct_same_shape_frames():
    frame = SyntheticThermalClip(1, with_target=True)[0]
    variants = augment(frame, seed=123)
    assert len(variants) >= 4
    assert all(v.shape == frame.shape for v in variants)
    assert any(not np.array_equal(v, frame) for v in variants)


def test_augment_fixed_seed_is_deterministic():
    frame = SyntheticThermalClip(1, with_target=True)[0]
    a = augment(frame, seed=99)
    b = augment(frame, seed=99)
    assert len(a) == len(b)
    assert all(np.array_equal(left, right) for left, right in zip(a, b))
