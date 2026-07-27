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
