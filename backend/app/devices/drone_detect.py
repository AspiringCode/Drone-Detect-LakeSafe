"""Drone-side thermal person detection: InfiRay P2 Pro -> YOLO -> signed alert.

Runs on the drone's Raspberry Pi from a repo checkout (needs ultralytics):

  python -m app.devices.drone_detect --api URL --drone-id ID --key drone.pem --lat 47.6 --lon -122.1 [--camera 0] [--model best.pt]
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Callable, Iterable

import cv2
import numpy as np

from app.detection.detector import ThermalDetector
from app.detection.temporal import TemporalPersistenceFilter
from app.devices import drone_link
from app.models import Detection

COOLDOWN_SECONDS = 30.0


def thermal_frame(frame: np.ndarray) -> np.ndarray:
    # The P2 Pro's UVC frame is 256x384: the top 256x192 is the palette image,
    # the bottom half is raw temperature bytes the detector cannot read.
    top = frame[: frame.shape[0] // 2]
    return cv2.cvtColor(top, cv2.COLOR_BGR2GRAY) if top.ndim == 3 else top


def run(frames: Iterable[np.ndarray], detector: ThermalDetector, persistence: TemporalPersistenceFilter,
        send: Callable[[Detection], bool], *, cooldown_s: float = COOLDOWN_SECONDS,
        clock: Callable[[], float] = time.monotonic) -> None:
    """Send the strongest confirmed detection, at most once per cooldown so one person in view is one alert."""
    last_sent: float | None = None
    for index, frame in enumerate(frames):
        confirmed = persistence.update(detector.detect(thermal_frame(frame), index))
        if not confirmed or (last_sent is not None and clock() - last_sent < cooldown_s):
            continue
        if send(max(confirmed, key=lambda d: d.confidence)):
            last_sent = clock()


def _camera_frames(index: int) -> Iterable[np.ndarray]:
    capture = cv2.VideoCapture(index)
    if not capture.isOpened():
        raise SystemExit(f"cannot open camera {index}")
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                raise SystemExit("camera stopped delivering frames")
            yield frame
    finally:
        capture.release()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LakeSafe drone thermal detection")
    parser.add_argument("--api", required=True)
    parser.add_argument("--drone-id", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--model", help="YOLO weights; defaults to the detector's stock model")
    # shortcut: fixed position per run; replace with the MAVLink bridge position at detection time.
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    args = parser.parse_args(argv)
    key = drone_link._load_key(args.key)

    def send(detection: Detection) -> bool:
        payload = {
            "confidence": detection.confidence, "bbox": list(detection.bbox),
            "detected_at": detection.timestamp.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "position": {"lat": args.lat, "lon": args.lon},
        }
        try:
            status, text = drone_link.post(args.api, f"/api/devices/{args.drone_id}/detections", key, args.drone_id, payload)
        except OSError as exc:
            # Unreachable backend: retry on the next confirmed frame rather than going quiet for a cooldown.
            print("detection not delivered:", exc, flush=True)
            return False
        print(status, text, flush=True)
        return True

    run(_camera_frames(args.camera), ThermalDetector(args.model, source="real"), TemporalPersistenceFilter(), send)
    return 0


if __name__ == "__main__":
    sys.exit(main())
