# Supabase Setup

Apply the migrations in order. The access foundation requires a local Supabase
environment because its RLS assertions are pgTAP tests:

```text
supabase db reset
supabase test db
supabase db lint --level error
cd backend
uv run pytest -q
```

The backend service role is server-only. Browser tokens establish identity, but
station verification, membership, and roles are reloaded from the database for
every operational request and WebSocket check.

Backend tests use `InMemoryBackend`; they do not require Supabase credentials or network access.

## Production release gate

Run these commands, in this order, for every release candidate:

```text
supabase db reset
supabase test db
supabase db lint --level error
cd backend
uv run pytest -q
cd ../dashboard
npm test -- --run
npm run build
git diff --check
```

The release is blocked if any command fails, including any failure drill in
`backend/tests/integration/test_failure_drills.py`. It is also blocked if a
public DTO gains a forbidden operational field, an operational table enters
the public Realtime publication, an audit mutation succeeds, a direct client
storage read succeeds, or cross-station access returns data. A local machine
without the Supabase CLI, Docker, or a running database cannot clear the
database portion of this gate; run those checks in the configured Supabase CI
or release environment before deployment.
