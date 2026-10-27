# Judge walkthrough and local setup

## Hosted application

Open **https://lakesafe.vercel.app**. Public lake browsing does not require an
account. For the interactive software demonstration, use the
[public judge credentials](demo-credentials.md). Private
administrator passwords and device keys are not included in this repository.

Prepared judge fixtures have a temporary password-only exception. Normal
operator access requires current verification, MFA, active station membership,
and the capability needed for the requested action. The seeded CAC exception
expires **January 1, 2027 at 00:00 America/Los_Angeles** (after December 31); judging after that date
requires the maintainer to arrange appropriate access. Public signup does not
grant station access.

The dashboard runs on Vercel; its FastAPI backend runs separately on Northflank.
Signing in to Supabase alone does not establish that the API is available.

## Suggested walkthrough

1. On the public home page, choose Beaver Lake, Lake Sammamish, or Pine Lake.
   Pan/zoom the map and inspect published notices, patrol presence, and freshness.
2. Sign in as **JUDGE_ALL** using the [demo credential handout](demo-credentials.md)
   and open **Lakes → Beaver Lake**. The other judge accounts each see one lake.
3. Select **Start simulation**, **Add simulated drone**, and **Regenerate zones**.
4. Choose **Detection observed**, **No detection observed**, or **Inconclusive**
   under **Demo second-drone finding**, then select **Simulate detection**.
5. Review the initial detector and location, the investigating drone, and its
   separate finding. Arrival alone is not corroboration.
6. **Confirm detection** keeps observation open. **Dismiss and resume patrol** or
   **End investigation and resume patrol** requests restoration of the original
   patrols. Observe the resulting state, not just the button click.
7. After two alerts in the same runtime session, use **Review an alert** to revisit
   an earlier one. Open **Alerts** and **Reports** for available lake-scoped records.
8. Choose **Stop simulation** when finished. Follow the
   [device workflow](demo-credentials.md#device-registration-and-mission-workflow)
   for registration, assignment, mission export and controls within the separate
   judge stations. The shared accounts cannot access existing original-station
   drones or manage station membership, lake creation or public visibility.

Within an authorized judge or private administrator station, **Drones → Add drone +**
opens Register, Assign lake, and Connect; mission preview/export does not arm or
launch a device. **Account → Stations → Manage station** provides member access
and lake setup. Station management requires private administrator access. Do not register or command a device without its owner's authorization.

Keep SIMULATED labels visible. Demo findings are generated, no camera clip is
recorded, and no emergency service is contacted. Simulation/review state may reset
when the API restarts. A software demo is not validation of physical drone flight
or drowning detection.

## Local prerequisites

- Git, Python 3.11 or newer, and `uv`.
- Node.js 24.11 or newer within major 24, with npm.
- A configured Supabase test project and test identities/memberships.
- Supabase CLI and Docker for a complete local database reset and pgTAP checks.

The tracked migration directory is authoritative and currently ends at
`0052_judge_station_device_access.sql`. Historical `0009` files now use
`000901` and `000902` versions. Follow the [database guide](../supabase/README.md);
do not reset the hosted judge project or assume migrations create auth passwords.

## Environment configuration

Create an untracked `backend/.env` with values for the intended test project:

```dotenv
SUPABASE_URL=<test-project-url>
SUPABASE_KEY=<public-project-key>
SUPABASE_SERVICE_ROLE_KEY=<server-only-service-role-key>
SUPABASE_JWT_ISSUER=<project-auth-issuer>
SUPABASE_JWT_AUDIENCE=authenticated
CORS_ALLOWED_ORIGINS=http://localhost:5173,http://localhost:5175
```

Legacy HS256 projects also need `SUPABASE_JWT_SECRET`; asymmetric tokens use
the project's verification-key path. Match the backend configuration to the
actual Supabase project rather than changing token validation to accept another
issuer.

Create an untracked `dashboard/.env.local`:

```dotenv
VITE_API_BASE_URL=http://localhost:8000
VITE_SUPABASE_URL=<same-test-project-url>
VITE_SUPABASE_ANON_KEY=<public-project-key>
```

Use the Vite URL printed at startup and allow that exact origin in backend CORS.
For a local frontend using the hosted API, set its API origin to
`https://site--lakesafe-api--cbq5jh567mfk.code.run`; the Vercel website is not an
API origin. This still reads/writes the hosted project, not an isolated local
database.

ID.me additionally requires `IDME_CLIENT_ID`, `IDME_CLIENT_SECRET`,
`IDME_REDIRECT_URI`, the provider-approved `IDME_SCOPE`,
`VERIFICATION_SESSION_ENCRYPTION_KEY`, and absolute
`IDME_PROFILE_SUCCESS_URL` / `IDME_PROFILE_FAILURE_URL` dashboard URLs.
Provider-approved affiliation claims must be tested before claiming enrollment
works. Missing configuration is reported unavailable. It is not needed for the
prepared CAC exception.

Real-device operation additionally uses the configured gateway transport and
signing material, heartbeat freshness/replay checks, and the device's own private
key. See the [Pi guide](../deploy/pi/README.md). Never place service-role,
JWT/provider/signing secrets or device private keys in a `VITE_` variable,
repository, recording, or judge handout.

## Start and test

In separate terminals, from the repository root:

```text
cd backend
uv sync --frozen
uv run uvicorn app.main:app --env-file .env --reload
```

```text
cd dashboard
npm ci
npm run dev
```

For application checks:

```text
cd backend
uv run pytest -q
cd ../dashboard
npm test
npm run build
cd ..
git diff --check
```

Database checks and their separate release evidence are described in
[`supabase/README.md`](../supabase/README.md). In-memory tests do not prove
hosted RLS, actual aircraft behavior, or third-party enrollment.

## Troubleshooting and remaining limits

- **Cannot check account access:** verify the API origin, backend availability,
  CORS, matching Supabase projects, and current station access.
- **Lake setup needs attention/queued:** inspect that lake's setup state. Its
  unavailability must not be mistaken for a complete, empty alert history.
- **503/no healthy upstream:** inspect Northflank instance health and logs. The
  hosted 512 MB service has experienced an out-of-memory restart; a reachable
  frontend does not guarantee an available API.
- **No public lake:** a newly added lake is private until an administrator
  publishes it. Public-page visibility is separate from join-request access.
- **No real drone position:** registration alone does not supply telemetry.
  Inspect current signed heartbeats; a test marker is labeled simulated.
- **Password recovery email:** the CAC setup uses Supabase's restricted default
  sender; unrestricted public email delivery is deferred.
- **ID.me unavailable:** partner application/policy/redirect setup is still an
  external integration requirement. Do not submit identity documents for the demo.

See the [AI assistance disclosure](ai-disclosure.md), [privacy/safety design](privacy-and-safety.md),
and [architecture](architecture-and-algorithms.md) for implementation boundaries.
