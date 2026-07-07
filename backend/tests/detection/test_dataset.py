from pathlib import Path

from app.detection.dataset import SyntheticThermalClip, load_clip, make_fixture_dataset


def test_synthetic_clip_has_warm_blob():
    clip = SyntheticThermalClip(n_frames=10, with_target=True)
    assert clip.shape[0] == 10
    assert (clip > 200).sum() > 0

    empty = SyntheticThermalClip(n_frames=10, with_target=False)
    assert (empty > 200).sum() == 0


def test_make_fixture_dataset_writes_loadable_clips(tmp_path: Path):
    make_fixture_dataset(tmp_path, n_positive=2, n_negative=1)
    clips = sorted((tmp_path / "clips").glob("*.npy"))
    labels = sorted((tmp_path / "labels").glob("*.txt"))
    assert len(clips) == 3
    assert len(labels) == 3
    assert load_clip(clips[0]).ndim == 3
