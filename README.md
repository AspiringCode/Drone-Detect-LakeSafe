# **[Open LakeSafe — lakesafe.vercel.app](https://lakesafe.vercel.app)**

LakeSafe is a web application for lake-safety stations to plan drone patrols,
review possible detections, and publish lake updates for visitors. Built for the
2026 Congressional App Challenge.

## Where it runs

| Component | Hosting | Link or access |
|---|---|---|
| Website/dashboard | Vercel | **[lakesafe.vercel.app](https://lakesafe.vercel.app)** |
| FastAPI backend | Northflank | [API documentation](https://site--lakesafe-api--cbq5jh567mfk.code.run/docs) |
| PostgreSQL database, authentication, and private evidence storage | Supabase | Accessed through the application; database administration and private evidence are not public browsing surfaces. |
| Source code and CI | GitHub | [AspiringCode/Drone-Detect-LakeSafe](https://github.com/AspiringCode/Drone-Detect-LakeSafe) |

The website and API are separate deployments. Vercel serves the interface;
Northflank handles operational requests and live updates; Supabase stores the
application data and verifies sign-ins. Public lake browsing requires no account.

## Start here

- **Visitors:** choose a public lake, explore its map, and read published notices
  and patrol updates. No account is required.
- **Judges:** use the [public simulation-only demo accounts](submission/demo-credentials.md),
  open **Lakes**, and select a lake card. Access lasts through December 31, 2026.
  Prepared CAC accounts have a temporary password-only exception; this is not
  the normal operator-enrollment policy.
- **Developers:** follow [local setup](submission/judge-setup.md) and the
  [database guide](supabase/README.md).

The public catalog initially includes **Beaver Lake, Lake Sammamish, and Pine
Lake**. Administrators can add other lakes covered by the King County shoreline
source. The Drone Test Field is a separate test area, not a public lake.

## Main workflows

| Workflow | What the application does |
|---|---|
| Public lake information | Interactive shoreline maps, public notices, and generalized published patrol presence, with freshness information. |
| Station operations | Authenticated lake maps, fleet status, patrol zones, and detection review, scoped to station membership and capabilities. |
| Patrol planning | Uses reviewed access/environment observations as proxy priority inputs and clips coverage zones to the shoreline. These are not historical drowning records or validated predictions. |
| Investigation review | Distinguishes the initial detection, a second drone's finding, and the operator's Confirm, Dismiss, or End decision. Arrival alone does not corroborate a detection. |
| Drone setup | Register a device public key, assign a lake, connect signed heartbeats, and inspect connection/upload status. Private keys stay on the device. |
| Mission review | Preview a patrol and download a Mission Planner `.waypoints` file. Queueing a patrol is separate from device-confirmed upload; arming remains with the pilot. |
| Lake and station administration | Find a lake by name, review its shoreline, and add it to an authorized station or create a new station. New lakes start private; administrators explicitly publish or hide public lake pages. |
| Alerts and reports | Review available records across assigned lakes. A lake awaiting setup is identified separately instead of hiding other lakes' records. |

## Try the software demonstration

1. Sign in using the [judge demo credentials](submission/demo-credentials.md) and open **Lakes → Beaver Lake**.
2. Choose **Start simulation**, **Add simulated drone**, then **Regenerate zones**.
3. Select a **Demo second-drone finding** and choose **Simulate detection**.
4. Review the detecting drone, location, and second-drone finding. Choose
   **Confirm detection** to keep observing, or **Dismiss and resume patrol**.
   **End investigation and resume patrol** ends continued observation.
5. Observe the simulated drones resume their original patrols. After two alerts,
   use **Review an alert** to revisit the session's records.
6. Open **Alerts** and **Reports** to review the demo records. Hardware and station
   administration workflows require separately authorized private accounts.

Simulation activity is labeled **SIMULATED**. Its findings are generated scenarios,
not camera observations, and the demo records no camera clip. Simulation state
and review history are session/runtime data and may reset when the backend
restarts. No emergency service is contacted.

## What is implemented, and what remains

The hosted website, station access controls, lake setup, simulation, review UI,
signed-device transport, mission export, and device acknowledgement paths are
implemented. The drone-side detector supports temporal filtering and an optional
YOLO model; a model-free thermal hot-spot mode is also available.

Software and disarmed integration checks do **not** establish reliable swimmer or
drowning detection, autonomous open-water flight, rescue performance, or agency
dispatch integration. Physical flight and end-to-end thermal-model validation
remain separate acceptance work. See the [Pi guide](deploy/pi/README.md).

Normal operator access requires verification, MFA, active station membership, and
the relevant role. **ID.me end-to-end enrollment still requires provider-approved
application, policy, and redirect configuration**; the application reports it
unavailable when that configuration is missing. Public email delivery is deferred;
the CAC setup uses Supabase's restricted default sender.

## Stack and local setup

- Dashboard: React, TypeScript, Vite, Leaflet.
- API: Python, FastAPI, authenticated WebSockets, Shapely/GeoPandas.
- Database and identity: Supabase PostgreSQL, Auth, row-level security.
- Hosting: Vercel dashboard and Northflank API.
- Checks: Pytest, Vitest, and database/RLS regression scripts.

Use Python 3.11 or newer, `uv`, and Node.js **24.11 or newer within major 24**.
Supply the environment values in the [setup guide](submission/judge-setup.md).

```text
# Terminal 1, from the repository root
cd backend
uv sync --frozen
uv run uvicorn app.main:app --env-file .env --reload

# Terminal 2, from the repository root
cd dashboard
npm ci
npm run dev
```

The API defaults to port 8000; Vite prints the dashboard URL. Set
`VITE_API_BASE_URL` to the API origin, not the Vercel website. Never place a
service-role key, device private key, or provider secret in a `VITE_` variable.

## Documentation

- [Judge walkthrough and local configuration](submission/judge-setup.md)
- [Architecture and algorithms](submission/architecture-and-algorithms.md)
- [Privacy and safety design](submission/privacy-and-safety.md)
- [Supabase migrations and database checks](supabase/README.md)
- [Raspberry Pi services and bench setup](deploy/pi/README.md)
- [AI assistance disclosure](submission/ai-disclosure.md)
- [Open-source and data attribution](submission/open-source-attribution.md)
