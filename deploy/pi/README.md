# Drone Raspberry Pi setup

These components connect an ArduPilot flight controller, thermal camera, and
optional visible-light camera to LakeSafe. Judges can use the
[website simulation](../../README.md#try-the-software-demonstration) without
building or flying this hardware.

**Status:** signed device transport, mission upload/acknowledgement, investigation,
and return logic exist in software. Disarmed and mocked checks are not validation
of autonomous open-water flight, thermal-model accuracy, or rescue performance.

## Components

| Service | Function |
|---|---|
| `lakesafe-bridge` | Reads MAVLink state, sends signed heartbeats, handles supported commands, and writes a local position file. |
| `lakesafe-detect` | Reads the USB P2 Pro, filters detections over time, and submits signed alerts at the bridge's position. Optional thermal recording. |
| `lakesafe-camera` | Records a separate CSI camera to timestamped H.264 transport-stream segments. Optional; not required for the bridge. |

The model-free thermal hot-spot mode does not identify a drowning person. YOLO
mode requires separately supplied compatible weights. No validated detection
accuracy is claimed for either mode here.

## 1. Packages and checkout

The supplied systemd units assume Raspberry Pi OS, user `pi`, and a checkout at
`/home/pi/Drone-Detect-LakeSafe`. Change their user and paths for another account.

```bash
sudo apt update
sudo apt install -y git python3-venv python3-opencv python3-picamera2 ffmpeg v4l-utils
git clone https://github.com/AspiringCode/Drone-Detect-LakeSafe.git ~/Drone-Detect-LakeSafe
cd ~/Drone-Detect-LakeSafe/backend
python3 -m venv --system-site-packages .venv
.venv/bin/pip install pymavlink cryptography
```

The repository may require GitHub access. Picamera2, OpenCV, and NumPy come from
the OS packages; avoid replacing their compatible NumPy with an unrelated pip
installation. `ultralytics` is loaded only when model weights are requested;
install and validate the model-specific dependencies separately for YOLO mode.

## 2. Device identity and API connection

In LakeSafe, open **Drones → select the station → Add drone +**. Generate the
device key on the Pi or its ground laptop:

```bash
cd ~/Drone-Detect-LakeSafe/backend
.venv/bin/python -m app.devices.drone_link keygen --key drone.pem
chmod 600 drone.pem
```

Register only the printed public key, manufacturer, and serial number. Assign the
registered device to its intended lake; the website provides the device ID and
connection commands. Keep the private key on the device and out of screenshots,
repositories, and videos. Provision it as `/etc/lakesafe/drone.pem`, readable only
by the service account, and point `LAKESAFE_KEY` at that file.

Set `LAKESAFE_API` to the API origin. For the hosted service this is
`https://site--lakesafe-api--cbq5jh567mfk.code.run`, not
`https://lakesafe.vercel.app`. For a laptop API on a hotspot, use its reachable
LAN address and start the local API with `--host 0.0.0.0`; the example hotspot
address is not universal. Signed requests require a synchronized clock.

For the supplied `pi` service account, install the generated private key before
starting the bridge:

```bash
sudo install -d -m 755 /etc/lakesafe
sudo install -o pi -g pi -m 600 drone.pem /etc/lakesafe/drone.pem
```

Use the website's Connect step for either the Pi serial connection or a ground
laptop receiving MAVLink. Start on a disarmed bench. A current signed heartbeat
should change the registered device from **Awaiting heartbeat** to its reported
state and place it on the assigned lake map. A **Place test marker** action is
explicitly simulated; it is not evidence of aircraft telemetry.

## 3. Cameras

The P2 Pro path expects its UVC YUYV frame layout, with a color image and raw
temperature data. Confirm the device index rather than assuming camera 0:

```bash
v4l2-ctl --list-devices
```

For the supported USB identifier, a restricted video-group udev rule is:

```bash
echo 'ACTION=="add", SUBSYSTEMS=="usb", ATTRS{idVendor}=="0bda", ATTRS{idProduct}=="5830", MODE="660", GROUP="video"' \
  | sudo tee /etc/udev/rules.d/60-p2pro.rules
sudo udevadm control --reload
sudo usermod -aG video pi
```

Reconnect the camera and refresh the user's group session. On a Pi Zero, connect
the P2 Pro through the USB data port and a data-capable OTG adapter. See the
[thermal-camera guide](../../docs/thermal-camera-pi-setup.md) for troubleshooting.

For the optional CSI camera, use the correct ribbon for the board and confirm:

```bash
rpicam-hello --list-cameras
```

Older OS images may call this `libcamera-hello`.

## 4. Configuration and services

Copy the [environment template](lakesafe.env.example), then replace its placeholders:

```bash
sudo mkdir -p /etc/lakesafe
sudo cp ~/Drone-Detect-LakeSafe/deploy/pi/lakesafe.env.example /etc/lakesafe/drone.env
sudo nano /etc/lakesafe/drone.env
mkdir -p /home/pi/footage
sudo cp ~/Drone-Detect-LakeSafe/deploy/pi/*.service /etc/systemd/system/
sudo systemctl daemon-reload
```

Check `LAKESAFE_API`, registered device ID, private-key path, MAVLink system ID,
serial/UDP endpoint, and baud rate. Leave `LAKESAFE_MODEL` empty for the hot-spot
mode. `LAKESAFE_RECORD` controls thermal recording; the separate camera service
also needs a valid output directory.

On a controlled disarmed bench, enable only the services you need:

```bash
sudo systemctl enable --now lakesafe-bridge lakesafe-detect
# Optional, only with the CSI camera and output folder configured:
sudo systemctl enable --now lakesafe-camera
journalctl -u lakesafe-bridge -u lakesafe-detect -f
```

Service restart is not proof that the device is healthy: inspect the logs and
the website's heartbeat, assignment, and command-acknowledgement state.

## 5. Mission and investigation boundaries

The website downloads Mission Planner `.waypoints` files in **QGC WPL 110**
format. The CLI also supports QGroundControl `.plan`; only that format carries
the exported geofence. Review launch coordinates, altitude, route, and fence in
the ground-control software before any flight.

Downloading is separate from queueing a patrol, and receiving a command is
separate from confirming its upload. The website does not arm the aircraft.
Pilot override remains authoritative. Update the companion bridge before testing
new investigation/return commands; do not infer physical acceptance from a
successful browser simulation.

## 6. Recording and cleanup

Thermal `thermal_*.avi` and visible `visible_*.ts` files use UTC names and
burned-in clocks to support alignment. A useful bench take must retain its real
provenance; generated browser events do not create real thermal evidence.

On the Pi, stop the services to finish the current recording before copying it:

```bash
sudo systemctl stop lakesafe-camera lakesafe-detect lakesafe-bridge
```

Then, from the laptop:

```bash
scp "pi@lakesafe-pod.local:/home/pi/footage/*" .
```

Replace the example hostname as needed. Monitor free disk space and stop
recording before powering down; interruption can lose the current segment.
Local video files are not part of a source-code deployment.
