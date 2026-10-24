"""Record the drone's visible-light camera (Raspberry Pi CSI ribbon port) for demo footage.

Runs on the drone's Pi beside drone_detect.py; the CSI camera is a separate device from the
USB P2 Pro, so the two never fight over a camera:

  python -m app.devices.pi_camera_record --out /home/pi/footage [--size 1280x720] [--fps 30] [--segment-s 300]

Needs Picamera2, which ships with Raspberry Pi OS (apt install python3-picamera2), so the venv
must be created with --system-site-packages. Files are named thermal_/visible_ + UTC start time,
and both carry a burned-in UTC clock, so the two views line up in an editor.
"""

from __future__ import annotations

import argparse
import signal
import sys
import time
from pathlib import Path


def segment_path(folder: Path, now: float | None = None) -> Path:
    return folder / time.strftime("visible_%Y%m%dT%H%M%SZ.ts", time.gmtime(now))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LakeSafe visible-light camera recorder")
    parser.add_argument("--out", required=True, help="folder for the recordings")
    parser.add_argument("--size", default="1280x720", help="WIDTHxHEIGHT; 1280x720 leaves a Pi Zero 2 W headroom for detection")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--bitrate", type=int, default=6_000_000)
    parser.add_argument("--segment-s", type=int, default=300, help="start a new file this often, so a crash loses one segment at most")
    parser.add_argument("--hflip", action="store_true", help="for a camera mounted upside down (with --vflip)")
    parser.add_argument("--vflip", action="store_true")
    args = parser.parse_args(argv)
    width, height = (int(v) for v in args.size.lower().split("x"))

    import cv2
    from libcamera import Transform
    from picamera2 import MappedArray, Picamera2
    from picamera2.encoders import H264Encoder
    from picamera2.outputs import FfmpegOutput

    folder = Path(args.out)
    folder.mkdir(parents=True, exist_ok=True)
    camera = Picamera2()
    camera.configure(camera.create_video_configuration(
        main={"size": (width, height)}, controls={"FrameRate": args.fps},
        transform=Transform(hflip=args.hflip, vflip=args.vflip)))

    def stamp(request) -> None:
        with MappedArray(request, "main") as m:
            cv2.putText(m.array, time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()), (10, height - 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

    camera.pre_callback = stamp
    stopping = []
    signal.signal(signal.SIGTERM, lambda *_: stopping.append(True))
    encoder = H264Encoder(bitrate=args.bitrate)
    # MPEG-TS, not MP4: a file cut off by a battery pull still plays.
    camera.start_recording(encoder, FfmpegOutput(str(segment_path(folder))))
    started = time.monotonic()
    print("recording to", folder, flush=True)
    try:
        while not stopping:
            time.sleep(0.5)
            if time.monotonic() - started >= args.segment_s:
                camera.stop_recording()
                camera.start_recording(encoder, FfmpegOutput(str(segment_path(folder))))
                started = time.monotonic()
    except KeyboardInterrupt:
        pass
    finally:
        camera.stop_recording()
    return 0


if __name__ == "__main__":
    sys.exit(main())
