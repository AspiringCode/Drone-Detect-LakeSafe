drop policy if exists "Owners can view their organizations" on public.organizations;
drop policy if exists "Owners can create their organizations" on public.organizations;
drop policy if exists "Owners can update their organizations" on public.organizations;
drop policy if exists "Owners can view their lakes" on public.lakes;
drop policy if exists "Owners can create lakes for their organizations" on public.lakes;
drop policy if exists "Owners can update lakes" on public.lakes;

alter table public.organizations enable row level security;
alter table public.organizations force row level security;
alter table public.lakes enable row level security;
alter table public.lakes force row level security;

-- RLS predicates must not query tables that resolve back to their own policies.
-- These tightly scoped SECURITY DEFINER predicates execute with row security
-- explicitly disabled, are search-path pinned, and are callable only by the
-- authenticated role for policy evaluation.  This is the Supabase-supported
-- security-definer pattern; it does not depend on an ambient caller bypass.
create or replace function private.is_platform_staff(required_role text)
returns boolean
language sql
stable
security definer
set search_path = ''
set row_security = off
as $$
  select exists (
    select 1
    from public.platform_staff_roles as staff_role
    where staff_role.user_id = auth.uid()
      and staff_role.role = required_role
      and staff_role.active
  );
$$;

create or replace function private.officer_verification_is_current(target_verification_id uuid)
returns boolean
language plpgsql
security definer
set search_path = ''
set row_security = off
as $$
declare
  current_verification public.officer_verifications%rowtype;
begin
  select * into current_verification
  from public.officer_verifications
  where verification_id = target_verification_id
  for update;

  if not found then
    return false;
  end if;

  if current_verification.status = 'verified'
    and current_verification.expires_at is not null
    and current_verification.expires_at <= now() then
    -- Demotion must never strand an active station without an administrator.
    -- Suspend only stations for which this user is the final current admin,
    -- then expire the verification in the same transaction.
    update public.stations as station
    set status = 'suspended', updated_at = now()
    where station.status = 'active'
      and exists (
        select 1
        from public.station_memberships as membership
        join public.station_membership_roles as membership_role
          on membership_role.membership_id = membership.membership_id
        where membership.station_id = station.station_id
          and membership.user_id = current_verification.user_id
          and membership.status = 'active'
          and membership_role.role = 'station_admin'
      )
      and not exists (
        select 1
        from public.station_memberships as other_membership
        join public.station_membership_roles as other_role
          on other_role.membership_id = other_membership.membership_id
        join public.officer_verifications as other_verification
          on other_verification.user_id = other_membership.user_id
        where other_membership.station_id = station.station_id
          and other_membership.user_id <> current_verification.user_id
          and other_membership.status = 'active'
          and other_role.role = 'station_admin'
          and other_verification.status = 'verified'
          and other_verification.revoked_at is null
          and (other_verification.expires_at is null or other_verification.expires_at > now())
      );

    update public.officer_verifications
    set status = 'expired',
        version = version + 1,
        updated_at = now()
    where verification_id = target_verification_id;

    update public.profiles
    set account_class = 'civilian',
        verification_version = verification_version + 1,
        updated_at = now()
    where user_id = current_verification.user_id;

    return false;
  end if;

  return current_verification.status = 'verified'
    and (current_verification.expires_at is null or current_verification.expires_at > now())
    and current_verification.revoked_at is null;
end;
$$;

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
  select private.jwt_aal() = 'aal2'
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

create or replace function private.has_station_role(
  target_station_id uuid,
  required_roles text[]
)
returns boolean
language sql
security definer
set search_path = ''
set row_security = off
as $$
  select auth.uid() is not null
    and private.is_active_station_member(auth.uid(), target_station_id)
    and exists (
      select 1
      from public.station_memberships as membership
      join public.station_membership_roles as membership_role
        on membership_role.membership_id = membership.membership_id
      where membership.station_id = target_station_id
        and membership.user_id = auth.uid()
        and membership.status = 'active'
        and membership_role.role = any(required_roles)
    );
$$;

revoke all on public.organizations, public.lakes,
  public.stations, public.station_requests, public.station_memberships,
  public.station_membership_roles, public.station_invitations,
  public.station_join_requests
  from public, anon, authenticated;

grant select, insert, update, delete on public.lakes to authenticated;
grant select on public.stations, public.station_memberships,
  public.station_membership_roles, public.station_requests,
  public.station_join_requests to authenticated;

create policy lakes_select_active_station_member
  on public.lakes for select to authenticated
  using (private.is_active_station_member(auth.uid(), station_id));

create policy lakes_insert_station_admin
  on public.lakes for insert to authenticated
  with check (private.has_station_role(station_id, array['station_admin']));

create policy lakes_update_station_admin
  on public.lakes for update to authenticated
  using (private.has_station_role(station_id, array['station_admin']))
  with check (private.has_station_role(station_id, array['station_admin']));

create policy lakes_delete_station_admin
  on public.lakes for delete to authenticated
  using (private.has_station_role(station_id, array['station_admin']));

create policy stations_select_active_station_member
  on public.stations for select to authenticated
  using (private.is_active_station_member(auth.uid(), station_id));

create policy station_memberships_select_self_or_station_admin
  on public.station_memberships for select to authenticated
  using (
    user_id = auth.uid()
    or private.has_station_role(station_id, array['station_admin'])
  );

create policy station_membership_roles_select_self_or_station_admin
  on public.station_membership_roles for select to authenticated
  using (
    exists (
      select 1 from public.station_memberships as membership
      where membership.membership_id = station_membership_roles.membership_id
        and (
          membership.user_id = auth.uid()
          or private.has_station_role(membership.station_id, array['station_admin'])
        )
    )
  );

create policy station_requests_select_requester_or_station_admin
  on public.station_requests for select to authenticated
  using (
    requested_by = auth.uid()
    or private.is_platform_staff('system_admin')
  );

create policy station_join_requests_select_self_or_station_admin
  on public.station_join_requests for select to authenticated
  using (
    user_id = auth.uid()
    or private.has_station_role(station_id, array['station_admin'])
  );

-- Deny private functions by default.  The three capability predicates below
-- are the narrowly-scoped helpers evaluated directly by RLS policies; public
-- verification RPCs retain their explicit authenticated grants from 0004.
revoke all on all functions in schema private from public, anon, authenticated;
grant execute on function private.is_active_station_member(uuid, uuid) to authenticated;
grant execute on function private.has_station_role(uuid, text[]) to authenticated;
grant execute on function private.is_platform_staff(text) to authenticated;
