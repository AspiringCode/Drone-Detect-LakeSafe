# Supabase database setup

Supabase provides PostgreSQL, authentication, private evidence storage, and
row-level security for LakeSafe. Browser requests use the public project key and
the user's session. Server-only operations use a backend service-role credential.

For the hosted demonstration, start with the [project README](../README.md) and
[judge setup guide](../submission/judge-setup.md). Judges do not need to reset
or recreate the hosted database.

## Migration history

[`migrations/`](migrations/) is the authoritative ordered schema history. It
currently ends at `0051_isolated_public_demo_stations.sql`, including lake setup,
judge access, member management, durable patrol commands, investigation decisions,
public-page visibility, December judge access, and isolated public simulations.

The historical duplicate `0009` filenames were replaced by
`000901_idme_verification_hardening.sql` and
`000902_lake_data_source_status.sql`. Preserve these filenames and their order;
do not reapply old copies under the original names. A hosted project upgraded
manually needs its migration history reconciled before using CLI deployment.

## Local database checks

Install the Supabase CLI and Docker, then run these from the repository root
against a **local development stack**:

```text
supabase start
supabase db reset
supabase test db
supabase db lint --level error
```

`db reset` destroys and recreates local database state. Never use a reset against
the hosted judge project. These commands do not provision private hosted judge
credentials or configure an ID.me partner application.

The pgTAP suite is under [`tests/database/`](tests/database/). Additional native
SQL regressions cover [website workflows](tests/website_workflows.sql),
[lake workspaces](tests/lake_workspaces.sql), and
[investigation/public visibility](tests/investigation_visibility.sql). Use their
transaction/rollback boundaries in a controlled test database; an in-memory
Python test is not proof that hosted RLS passed.

## Access and data boundaries

- Operational authority is reloaded from verification, active station membership,
  and roles for REST and WebSocket requests; browser-supplied roles are not trusted.
- Public pages read dedicated public projections. They do not expose precise
  aircraft positions, device identifiers, private evidence, or station memberships.
- New lakes are not automatically published. Administrators explicitly control
  public lake-page visibility; this does not grant membership.
- Signed device reports and durable command acknowledgements are distinct from
  simulation events. Retirement revokes device access while retaining history.
- Service-role credentials and ID.me/signing secrets belong only in the backend.
  Device private keys belong on the device. Do not commit filled environment files.

CAC judge fixtures have a narrowly scoped, expiring password-only exception.
Ordinary operator access still requires verification and MFA. The
[public judge handout](../submission/demo-credentials.md) contains only shared
simulation credentials, valid through December 31, 2026. Private administrator
credentials remain outside the repository; public signup creates neither type.

Public judge memberships use `demo_operator`, limited to reading operations,
reviewing alerts, and changing simulated circulation on `simulation_only` stations.
The API caps that role even if another role is accidentally added. Database guards
reject real inventory in those stations and prevent conversion to physical
stations. Their demo lake runtimes are rebuilt from reviewed catalog geometry,
without copying another station's live fleet or alerts.

## Application checks and release evidence

```text
cd backend
uv sync --frozen
uv run pytest -q
cd ../dashboard
npm ci
npm test
npm run build
cd ..
git diff --check
```

Python tests primarily use isolated repositories and mocks; they do not establish
hosted database or aircraft acceptance. GitHub Actions runs backend and frontend
checks in [Checks](../.github/workflows/checks.yml); it does not currently run
the local Supabase/pgTAP commands above. Keep database results separate from CI.

A database/security release must pass migration, lint, RLS, audit, storage, and
cross-station checks in its target test environment. Block publication if a public
DTO exposes operational fields, an audit mutation succeeds, direct client access
to private evidence succeeds, or cross-station reads return data. A missing CLI,
Docker engine, or running database means those checks were not performed.
