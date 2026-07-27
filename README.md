# CAC Drone Lake Surveillance — Software

Congressional App Challenge 2026 entry (WA-08). The software "app" for an autonomous
multi-drone thermal drowning-detection concept for **Lake Sammamish**, built for and aligned
with the **LakeSafe Initiative** mission.

## What this is

Four decoupled software subsystems, integrated into one operator-facing demo:

1. **Risk-zone algorithm** — King County water/incident data → weighted risk zones over Lake Sammamish → heat map.
2. **Thermal detection pipeline** — YOLOv8n fine-tune + temporal-persistence filtering + evaluation.
3. **Multi-drone coordination simulation** — risk-weighted zone assignment, collision avoidance, battery reassignment, second-drone confirmation protocol.
4. **Operator dashboard** — real-time lake map, live drone positions, risk overlay, GPS-located alerts, one-tap dispatch.

Backend: Python 3.11+ / FastAPI / WebSocket. Dashboard: React + TypeScript + Vite + Leaflet. Storage: Supabase.

## Scope

This is a **proof-of-concept**, not an operational deployment. Specifically:

- **Not** a replacement for lifeguards, and **not** a 24/7 monitoring system.
- Open-water nighttime detection accuracy is **not** proven equal to pool-environment benchmarks.
- **Not** integrated with any real King County 911 CAD system. The dashboard receives **simulated/demo alerts only** — never live dispatch traffic.
- **Real vs. simulated is labeled everywhere.** Single-pod thermal footage is *real*; the 5-drone coordination and wide-area coverage are *simulated*. Every drone, detection, and alert record carries a `source: "real" | "simulated"` field, surfaced in the UI as a `SIMULATED`/`REAL` badge. Reliable classification happens at investigate altitude (~8–15 m), not wide-area scan altitude.

Lake Sammamish drowning statistics are cited as motivation and context, not as a claim this system would have prevented any specific incident.

## Running

```bash
# Backend
cd backend && pip install -e .        # or: uv sync
uvicorn app.main:app --reload

# Dashboard
cd dashboard && npm install && npm run dev

# Supabase: apply supabase/migrations/0001_init.sql, set env vars (see supabase/README.md)
```

Fire the demo: `POST /api/demo/trigger` → watch a detection become a confirmed, GPS-located alert on the dashboard.

### ID.me officer verification

The FastAPI service begins ID.me OIDC verification at
`POST /api/verifications/idme/start` and receives its callback at
`GET /api/verifications/idme/callback`. Configure backend-only environment
variables (never a `VITE_` browser variable): `IDME_CLIENT_ID`,
`IDME_CLIENT_SECRET`, `IDME_REDIRECT_URI`, and `IDME_AUDIENCE`. Optional
provider/environment overrides are `IDME_ISSUER`, `IDME_AUTHORIZATION_ENDPOINT`,
`IDME_TOKEN_ENDPOINT`, `IDME_JWKS_URI`, `IDME_PROFILE_SUCCESS_URL`, and
`IDME_PROFILE_FAILURE_URL`.
