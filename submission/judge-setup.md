# Judge setup and local demo guide

This guide runs the source locally. It contains no credentials. Values in angle brackets
are placeholders and must be supplied through a private environment; never commit a
filled-in copy.

## Prerequisites

- Git
- Python 3.11 or newer and `uv`
- Node.js/npm compatible with the committed dashboard lock file
- Supabase CLI and Docker for a complete local database/reset/test environment
- A Supabase project or local Supabase stack configured with test-only users and station
  membership for authenticated operational screens

## Install and start

In separate terminals from the repository root:

```text
cd backend
uv sync
uv run uvicorn app.main:app --reload
```

```text
cd dashboard
npm ci
npm run dev
```

The dashboard dev server normally prints its local URL. The backend default is
`http://localhost:8000`; set `VITE_API_BASE_URL` if the service uses another origin.

## Environment variable names

Backend variables found in `backend/app`:

```text
SUPABASE_URL=<local-or-test-supabase-url>
SUPABASE_KEY=<public-anon-key-for-server-public-projection-client>
SUPABASE_SERVICE_ROLE_KEY=<server-only-service-role-secret>
SUPABASE_JWT_SECRET=<server-only-legacy-hs256-verification-secret-if-used>
SUPABASE_JWT_ISSUER=<expected-token-issuer>
SUPABASE_JWT_AUDIENCE=<expected-token-audience>

IDME_CLIENT_ID=<provider-client-id>
IDME_CLIENT_SECRET=<server-only-provider-secret>
IDME_REDIRECT_URI=<backend-callback-url>
IDME_ISSUER=<provider-issuer>
IDME_AUDIENCE=<provider-audience>
IDME_AUTHORIZATION_ENDPOINT=<provider-authorization-url>
IDME_TOKEN_ENDPOINT=<provider-token-url>
IDME_JWKS_URI=<provider-jwks-url>
IDME_USERINFO_ENDPOINT=<provider-userinfo-url>
VERIFICATION_SESSION_ENCRYPTION_KEY=<server-only-fernet-key>
IDME_PROFILE_SUCCESS_URL=<dashboard-success-route>
IDME_PROFILE_FAILURE_URL=<dashboard-failure-route>

RISK_CONNECTOR_REFRESH_HOURS=<integer-hours>
DEVICE_CLOCK_SKEW_SECONDS=<integer-seconds>
REAL_HEARTBEAT_TTL_SECONDS=<integer-seconds>
REAL_GATEWAY_URL=<server-only-gateway-url>
REAL_GATEWAY_SIGNING_KEY_REF=<server-only-secret-reference>
REAL_GATEWAY_SIGNING_KEY=<server-only-resolved-hmac-secret>
```

Dashboard variables found in `dashboard/src`:

```text
VITE_API_BASE_URL=<backend-origin>
VITE_SUPABASE_URL=<local-or-test-supabase-url>
VITE_SUPABASE_ANON_KEY=<public-anon-key>
```

Never put the service-role key, ID.me secret, verification encryption key, JWT secret,
or real-device signing secret in a `VITE_` variable. Those values are backend-only.

## Supabase migration order

`supabase db reset` applies the migrations in filename order. The current sequence is:

```text
0001_init.sql
0002_orgs_lakes.sql
0003_identity_foundation.sql
0004_officer_verification.sql
0005_station_access.sql
0006_station_lake_cutover.sql
0007_station_rls.sql
0008_station_verification_workflows.sql
0009_idme_verification_hardening.sql
0009_lake_data_source_status.sql
0010_station_review_self_approval.sql
0011_risk_snapshots_zone_plans.sql
0012_atomic_zone_plan_persistence.sql
0013_risk_refresh_worker.sql
0014_risk_refresh_worker_hardening.sql
0015_risk_refresh_claim_tokens.sql
0016_risk_refresh_publish_lease.sql
0017_risk_refresh_atomic_publish.sql
0018_simulated_inventory_autonomy.sql
0019_autonomy_outbox_commit.sql
0020_simulated_inventory_api.sql
0021_real_device_gateway.sql
0022_real_heartbeat_capacity.sql
0023_atomic_real_heartbeat_queue.sql
0024_real_command_acknowledgements.sql
0025_real_outbox_claim_scope.sql
0026_real_fleet_safety.sql
0027_real_delivery_retry_and_safe_return_ack.sql
0028_real_command_expired_reconciliation.sql
0029_alerts_public_projections.sql
0030_audit_storage_hardening.sql
0031_real_safety_request_reconciliation.sql
0032_thermal_evidence_hardening.sql
0033_rls_regression_and_grants.sql
0034_privileged_rate_limits.sql
0035_rate_limit_and_safety_idempotency_hardening.sql
0036_reviewed_multi_lake_sources.sql
```

Do not rename one of the two `0009` migrations casually; their current lexical ordering
is part of the checked-in history.

## Database and release gates

Run the commands specified by `supabase/README.md` from the repository root:

```text
supabase db reset
supabase test db
supabase db lint --level error
cd backend
uv run pytest -q
cd ../dashboard
npm test -- --run
npm run build
cd ..
git diff --check
```

Any failure blocks the release. A machine without the Supabase CLI, Docker, or a running
database cannot claim the database portion passed.

## Local demonstration flow

1. Start the local Supabase stack and apply all migrations through `0036`.
2. Configure a test user with current officer verification, MFA (`aal2`), active station
   membership, and the minimum role needed for each action. Use only test identities.
3. Start the backend and dashboard with the environment names above.
4. Open the civilian screens first and show only generalized/delayed projections.
5. Sign in as the prepared station member, select Lake Sammamish, Pine Lake, and Beaver
   Lake, and show source attribution plus proxy-priority/baseline coverage labels.
6. Queue a simulated circulation eligibility change and show its reconciliation plus
   desired/acknowledged versions; explain that this action does not rebuild the displayed
   zone plan. Then trigger a demo alert. Keep every SIMULATED label visible and say that
   no 911/CAD feed or physical aircraft is connected.
7. Do not enable the real adapter unless a separately controlled hardware test has been
   authorized and configured; local judges do not need it for the software demo.

## Pre-submission setup gaps

- No stable hosted judge URL is documented.
- No dedicated judge credentials are documented.
- No checked-in `.env.example` exists.
- No one-command reset-and-seed flow exists.

Resolve these gaps before relying on remote judging. Until then, this source setup is the
truthful path and requires a maintainer to provision test identities and database state.
