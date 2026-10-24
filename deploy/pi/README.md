# Drone Raspberry Pi setup

Three services run on each drone's Pi (Raspberry Pi OS, user `pi`):

| Service | What it does |
|---|---|
| `lakesafe-bridge` | ArduPilot MAVLink → signed heartbeats, writes the live position file |
| `lakesafe-detect` | InfiRay P2 Pro (USB) → hot-spot or YOLO detection → signed alert; with `LAKESAFE_RECORD` set, also saves the boxed thermal view |
| `lakesafe-camera` | Pi camera (CSI ribbon port) → timestamped H.264 `.ts` segments for demo footage |

## 1. Packages and checkout

```bash
sudo apt install -y git python3-venv python3-opencv python3-picamera2 ffmpeg v4l-utils
git clone <repo> ~/Drone-Detect-LakeSafe && cd ~/Drone-Detect-LakeSafe/backend
# --system-site-packages: Picamera2 and the Pi's OpenCV come from apt, not pip.
python3 -m venv --system-site-packages .venv
.venv/bin/pip install pymavlink cryptography   # numpy comes with python3-opencv; a pip numpy can break it
```

`drone_detect` only imports `ultralytics` when `LAKESAFE_MODEL` points at weights; the
model-free hot-spot detector needs none of it.

## 2. P2 Pro access without root

The P2 Pro is a UVC camera (USB id `0bda:5830`); its frame is 256x384 YUYV, the top half the
colour image and the bottom half 16-bit temperatures. `drone_detect.py` reads it with OpenCV
the same way [LeoDJ/P2Pro-Viewer](https://github.com/LeoDJ/P2Pro-Viewer) (MIT) does. That
project's udev rule lets the `pi` user open it:

```bash
echo 'ACTION=="add", SUBSYSTEMS=="usb", ATTRS{idVendor}=="0bda", ATTRS{idProduct}=="5830", MODE="660", GROUP="video"' \
  | sudo tee /etc/udev/rules.d/60-p2pro.rules
sudo udevadm control --reload && sudo usermod -aG video pi
v4l2-ctl --list-devices        # note the /dev/videoN; pass --camera N if it isn't 0
```

On a Pi Zero 2 W the camera goes in the **USB** micro-USB port (not PWR IN) through a data OTG
adapter. More troubleshooting: `docs/thermal-camera-pi-setup.md`.

## 3. Pi camera

Connect the camera to the CSI port (a Pi Zero needs the narrow 22-pin ribbon), then:

```bash
rpicam-hello --list-cameras     # must list the sensor (older OS: libcamera-hello)
```

## 4. Config and services

```bash
sudo mkdir -p /etc/lakesafe && sudo cp ~/Drone-Detect-LakeSafe/deploy/pi/lakesafe.env.example /etc/lakesafe/drone.env
sudo nano /etc/lakesafe/drone.env      # drone id, API address, LAKESAFE_RECORD
mkdir -p /home/pi/footage
sudo cp ~/Drone-Detect-LakeSafe/deploy/pi/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lakesafe-bridge lakesafe-detect lakesafe-camera
journalctl -fu lakesafe-camera         # "recording to /home/pi/footage"
```

## 5. Footage

Both recordings are named by UTC start time (`thermal_…avi`, `visible_…ts`) and carry a
burned-in UTC clock, so they line up side by side in a video editor. Copy them to the laptop:

```bash
scp "pi@lakesafe-pod.local:/home/pi/footage/*" .
```

A Pi Zero 2 W SD card fills at roughly 2.7 GB per hour of 720p video; clear the folder between
flights. Stop the services before powering down when you can; a file cut off by a battery pull
still plays, but its last second may be lost.
