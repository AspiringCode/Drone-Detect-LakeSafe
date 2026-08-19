# LakeSafe — Congressional App Challenge software

LakeSafe is a safety-oriented proof-of-concept for three reviewed King County lakes:
**Lake Sammamish, Pine Lake, and Beaver Lake**. It combines reviewed public access and
environmental proxy observations, shoreline-clipped planning, role-separated public and
station views, and a clearly labeled fleet/alert simulation.

Backend: Python 3.11+ / FastAPI / WebSocket. Dashboard: React / TypeScript / Vite /
Leaflet. Storage and authorization: Supabase/PostgreSQL.

## Current scope

- Reviewed King County swim-beach observations and monitoring-site coordinates are real
  public proxy data; they are not incident history.
- Reviewed King County polygons supply the three local shoreline fixtures.
- Planning creates proxy-priority and baseline-coverage cells, validates shoreline-
  clipped geometry, and atomically retains safe active state across refresh failures.
- Fleet coordination and demo alerts are simulated.
- A signed real-device software pathway exists but has not been physically flight-
  validated.
- Thermal detector code exists, but real open-water accuracy, false-positive rate, and
  latency are unproven. There is no live CAD/911 integration.
- Civilian output is delayed/generalized; operational access requires verified/MFA/
  station/capability checks and database row-level security.

Draft CAC materials, setup instructions, AI disclosure, architecture, results,
privacy notes, and attribution are in [`submission/`](submission/).

## Local development

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

The full database release gate and every environment-variable name are documented in
[`submission/judge-setup.md`](submission/judge-setup.md). Apply Supabase migrations in
filename order through `0037_risk_plan_safety_reserve.sql`; never place service-role,
identity-provider, or real-device secrets in browser-exposed `VITE_` variables.

## Transparency

All AI assistance must be disclosed accurately. The draft disclosure names Codex and
Claude and requires student personalization. Open-source and data terms—including GSAP's
Standard License, Ultralytics deployment review, King County sources, and OpenStreetMap
attribution—are documented in [`submission/open-source-attribution.md`](submission/open-source-attribution.md).
