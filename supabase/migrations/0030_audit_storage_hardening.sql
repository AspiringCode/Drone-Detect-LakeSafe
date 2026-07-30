-- Security decisions are append-only, including when written through service role.
alter table public.audit_events enable row level security;
alter table public.audit_events force row level security;

alter table public.audit_events drop constraint if exists audit_events_exactly_one_actor;
alter table public.audit_events add constraint audit_events_exactly_one_actor
  check ((actor_user_id is null) <> (actor_device_id is null));

create or replace function private.reject_audit_mutation()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  raise exception 'audit_events are append-only' using errcode = '42501';
end;
$$;

drop trigger if exists audit_events_append_only on public.audit_events;
drop trigger if exists reject_audit_update_delete on public.audit_events;
create trigger reject_audit_update_delete
  before update or delete on public.audit_events
  for each row execute function private.reject_audit_mutation();

revoke all on public.audit_events from public, anon, authenticated;
revoke all on function private.reject_audit_mutation() from public, anon, authenticated;
grant select on public.audit_events to authenticated;

drop policy if exists audit_events_select_scoped on public.audit_events;
create policy audit_events_select_scoped
  on public.audit_events
  for select to authenticated
  using (
    exists (
      select 1 from public.platform_staff_roles as staff
      where staff.user_id = auth.uid() and staff.role = 'system_admin' and staff.active
    )
    or (
      station_id is not null and exists (
        select 1
        from public.station_memberships as membership
        join public.station_membership_roles as membership_role
          on membership_role.membership_id = membership.membership_id
        join public.officer_verifications as verification
          on verification.user_id = membership.user_id
        where membership.station_id = audit_events.station_id
          and membership.user_id = auth.uid()
          and membership.status = 'active'
          and membership_role.role = 'station_admin'
          and private.officer_verification_is_current(verification.verification_id)
      )
    )
  );
