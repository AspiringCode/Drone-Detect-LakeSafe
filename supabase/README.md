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
