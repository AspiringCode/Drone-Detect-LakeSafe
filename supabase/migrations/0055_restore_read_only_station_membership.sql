-- Preserve the read-only RLS predicate from 0042 after the fixture rollback.
-- PostgREST GET transactions cannot run the verification maintenance helper.
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
        and verification.status = 'verified'
        and verification.revoked_at is null
        and (verification.expires_at is null or verification.expires_at > now())
    );
$$;
