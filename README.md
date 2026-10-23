# LakeSafe

LakeSafe is a lake-safety platform for coordinating drone patrols over local lakes. It
divides each lake into patrol zones, shows where coverage matters most, and gives
public-safety stations a live view of their fleet and alerts. Civilians get a separate,
privacy-safe view of lake status.

Built for the 2026 Congressional App Challenge. It currently covers three King County
lakes: **Lake Sammamish, Pine Lake, and Beaver Lake**.

## What it does

- **Patrol planning.** Pulls King County swim-beach and water-monitoring data, marks the
  areas that need the most attention, and splits each lake into patrol zones clipped to
  the real shoreline.
- **Station dashboard.** Verified public-safety members see a live lake map, drone
  positions, patrol zones, and alerts for their own station's lakes only.
- **Civilian view.** The public sees lake status and alerts by general area, delayed, with
  no exact drone positions or operational details.
- **Thermal detection.** A YOLO-based detector with a filter that only reports a person
  when they appear across several consecutive frames.
- **Mission export.** Exports a zone's patrol route as a QGroundControl `.plan` file for
  ArduPilot drones.
- **Access control.** Officer verification, multi-factor sign-in, station roles, and
  database row-level security.

In this version, drone flight and alerts are simulated; the app has not been flown with
real aircraft yet.

## Tech stack

- **Backend:** Python, FastAPI, WebSockets, Shapely/GeoPandas
- **Dashboard:** React, TypeScript, Vite, Leaflet
- **Database and auth:** Supabase (PostgreSQL)
- **Tests:** Pytest, Vitest

## Running it locally

```text
# Backend
cd backend
uv sync
uv run uvicorn app.main:app --reload

# Dashboard (separate terminal)
cd dashboard
npm ci
npm run dev
```

Environment variables and database setup are in
[`submission/judge-setup.md`](submission/judge-setup.md).

To let a drone's Raspberry Pi on the laptop's Wi-Fi hotspot reach the backend, start it
with `--host 0.0.0.0`. The Pi side is in [`deploy/pi/`](deploy/pi/).

## More detail

- [Architecture and algorithms](submission/architecture-and-algorithms.md)
- [Privacy and safety design](submission/privacy-and-safety.md)
- [AI assistance disclosure](submission/ai-disclosure.md)
- [Open-source and data attribution](submission/open-source-attribution.md)
