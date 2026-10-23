-- Time-boxed fictional CAC judge sessions. The table is the authority;
-- only postgres provisioning may write it, and backend service reads expiry.
create table public.cac_judge_access (
  user_id uuid primary key references auth.users(id) on delete cascade,
  expires_at timestamptz not null,
  created_at timestamptz not null default now(),
  constraint cac_judge_access_expiry_window check (
    expires_at > created_at
    and expires_at <= timestamptz '2026-11-01 07:00:00+00'
  )
);
alter table public.cac_judge_access enable row level security;
alter table public.cac_judge_access force row level security;
revoke all on table public.cac_judge_access from public, anon, authenticated, service_role;
grant select on table public.cac_judge_access to service_role;

-- Validate trusted provisioning metadata once; expiry/row revocation remain
-- the shared per-request authority for backend and RLS.
create function private.validate_cac_judge_provisioning()
returns trigger language plpgsql security definer
set search_path = '' set row_security = off as $$
begin
  if not exists (
    select 1 from auth.users as user_record
    where user_record.id = new.user_id
      and user_record.raw_app_meta_data @>
        '{"fictional_demo":true,"fixture_set":"cac-2026-operators"}'::jsonb
  ) then
    raise exception 'judge access requires a trusted fictional CAC fixture account'
      using errcode = '23514';
  end if;
  return new;
end;
$$;
revoke all on function private.validate_cac_judge_provisioning() from public, anon, authenticated, service_role;
create trigger cac_judge_access_validate_fixture
before insert or update on public.cac_judge_access
for each row execute function private.validate_cac_judge_provisioning();

create function private.station_session_is_allowed()
returns boolean language sql stable security definer
set search_path = '' set row_security = off as $$
  select private.jwt_aal() = 'aal2'
    or exists (
      select 1 from public.cac_judge_access as access
      where access.user_id = auth.uid() and access.expires_at > now()
    );
$$;
revoke all on function private.station_session_is_allowed() from public, anon, authenticated, service_role;

create or replace function private.is_active_station_member(
  target_user_id uuid,
  target_station_id uuid
)
returns boolean
language sql
security definer
set search_path = ''
set row_security = off
as $$
  select private.station_session_is_allowed()
    and exists (
      select 1
      from public.stations as station
      join public.station_memberships as membership
        on membership.station_id = station.station_id
      join public.officer_verifications as verification
        on verification.user_id = membership.user_id
      where station.station_id = target_station_id
        and station.status = 'active'
        and membership.user_id = target_user_id
        and membership.status = 'active'
        and private.officer_verification_is_current(verification.verification_id)
    );
$$;
