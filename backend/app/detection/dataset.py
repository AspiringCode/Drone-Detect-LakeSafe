from __future__ import annotations

from pathlib import Path

import numpy as np

ThermalFrame = np.ndarray


def SyntheticThermalClip(
    n_frames: int,
    with_target: bool,
    height: int = 96,
    width: int = 128,
    seed: int = 7,
) -> np.ndarray:
    rng = np.random.default_rng(seed + (1 if with_target else 0) + n_frames)
    clip = rng.normal(loc=55, scale=6, size=(n_frames, height, width)).clip(25, 95)

    if with_target:
        yy, xx = np.mgrid[0:height, 0:width]
        for idx in range(n_frames):
            cx = width * 0.45 + idx * 0.8
            cy = height * 0.52 + np.sin(idx / 2) * 1.5
            sigma = 2.8
            blob = np.exp(-(((xx - cx) ** 2) + ((yy - cy) ** 2)) / (2 * sigma**2))
            shoulders = np.exp(-(((xx - cx) ** 2) / (2 * 5.0**2) + ((yy - (cy + 4)) ** 2) / (2 * 2.2**2)))
            clip[idx] += blob * 175 + shoulders * 90

    return clip.clip(0, 255).astype(np.uint8)


def load_clip(path: str | Path) -> np.ndarray:
    return np.load(Path(path))


def _small_rotation(frame: np.ndarray, shift: int) -> np.ndarray:
    rotated = np.roll(frame, shift=shift, axis=0)
    return np.roll(rotated, shift=-shift, axis=1)


def augment(frame: np.ndarray, seed: int) -> list[np.ndarray]:
    """Return deterministic thermal-plausible single-channel augmentations.

    Horizontal flip covers approach angle, small integer-pixel rotation/shift
    approximates platform motion, gaussian noise models sensor grain, occlusion
    patches model wave/spray masking, and contrast jitter models warm-water delta.
    """
    rng = np.random.default_rng(seed)
    base = frame.astype(np.float32)
    variants: list[np.ndarray] = []

    variants.append(np.fliplr(base).clip(0, 255).astype(np.uint8))
    variants.append(_small_rotation(base, int(rng.integers(-2, 3))).clip(0, 255).astype(np.uint8))

    noisy = base + rng.normal(0, 5, size=base.shape)
    variants.append(noisy.clip(0, 255).astype(np.uint8))

    occluded = base.copy()
    h, w = occluded.shape
    patch_h = max(4, h // 10)
    patch_w = max(6, w // 9)
    y = int(rng.integers(0, max(1, h - patch_h)))
    x = int(rng.integers(0, max(1, w - patch_w)))
    occluded[y : y + patch_h, x : x + patch_w] = rng.normal(70, 8, size=(patch_h, patch_w))
    variants.append(occluded.clip(0, 255).astype(np.uint8))

    factor = float(rng.uniform(0.85, 1.2))
    midpoint = float(base.mean())
    contrast = (base - midpoint) * factor + midpoint
    variants.append(contrast.clip(0, 255).astype(np.uint8))

    return variants


def make_fixture_dataset(
    root: str | Path | None = None,
    n_positive: int = 10,
    n_negative: int = 3,
    n_frames: int = 1,
) -> Path:
    base = Path(root) if root is not None else Path(__file__).resolve().parents[2] / "fixtures" / "thermal"
    clips_dir = base / "clips"
    labels_dir = base / "labels"
    clips_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    for idx in range(n_positive):
        clip = SyntheticThermalClip(n_frames, with_target=True, seed=100 + idx)
        name = f"positive_{idx:03d}"
        np.save(clips_dir / f"{name}.npy", clip)
        (labels_dir / f"{name}.txt").write_text("0 0.45 0.54 0.08 0.10\n", encoding="utf-8")

    for idx in range(n_negative):
        clip = SyntheticThermalClip(n_frames, with_target=False, seed=200 + idx)
        name = f"negative_{idx:03d}"
        np.save(clips_dir / f"{name}.npy", clip)
        (labels_dir / f"{name}.txt").write_text("", encoding="utf-8")

    return base
