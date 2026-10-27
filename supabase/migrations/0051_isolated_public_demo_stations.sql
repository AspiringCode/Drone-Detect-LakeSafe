-- Public judge credentials are scoped to isolated, simulation-only stations.
begin;
alter table public.stations add column simulation_only boolean not null default false;
alter table public.lakes add column demo_source_lake_id text check (
  demo_source_lake_id in ('lake-beaver','lake-sammamish','lake-pine')
);
alter table public.station_membership_roles drop constraint station_membership_roles_role_check;
alter table public.station_membership_roles add constraint station_membership_roles_role_check
  check (role in ('viewer','dispatcher','safety_supervisor','station_admin','demo_operator'));

create function private.guard_simulation_station() returns trigger
language plpgsql set search_path='' as $$
begin
  if old.simulation_only and not new.simulation_only then
    raise exception 'simulation stations cannot become physical stations' using errcode='23514';
  end if;
  if new.simulation_only and exists (
    select 1 from public.drone_inventory where station_id=new.station_id and source='real'
  ) then
    raise exception 'simulation station cannot contain real devices' using errcode='23514';
  end if;
  return new;
end; $$;
create trigger simulation_station_guard before update of simulation_only on public.stations
for each row execute function private.guard_simulation_station();

create function private.guard_simulation_inventory() returns trigger
language plpgsql set search_path='' as $$
begin
  if new.source='real' and exists (
    select 1 from public.stations where station_id=new.station_id and simulation_only
  ) then
    raise exception 'real devices are not allowed in simulation stations' using errcode='23514';
  end if;
  return new;
end; $$;
create trigger simulation_inventory_guard before insert or update of station_id,source on public.drone_inventory
for each row execute function private.guard_simulation_inventory();

create function private.guard_demo_lake_source() returns trigger
language plpgsql set search_path='' as $$
begin
  if new.demo_source_lake_id is not null and not exists (
    select 1 from public.stations where station_id=new.station_id and simulation_only
  ) then
    raise exception 'demo lake requires a simulation station' using errcode='23514';
  end if;
  return new;
end; $$;
create trigger demo_lake_source_guard before insert or update of station_id,demo_source_lake_id on public.lakes
for each row execute function private.guard_demo_lake_source();

create or replace function private.is_active_station_member(target_user_id uuid,target_station_id uuid)
returns boolean language sql security definer set search_path='' set row_security=off as $$
  select private.station_session_is_allowed() and exists (
    select 1 from public.stations station
    join public.station_memberships membership on membership.station_id=station.station_id
    join public.officer_verifications verification on verification.user_id=membership.user_id
    where station.station_id=target_station_id and station.status='active'
      and membership.user_id=target_user_id and membership.status='active'
      and verification.status='verified' and verification.revoked_at is null
      and (verification.expires_at is null or verification.expires_at>now())
      and (station.simulation_only or not exists (
        select 1 from public.station_membership_roles role
        where role.membership_id=membership.membership_id and role.role='demo_operator'
      ))
  );
$$;
revoke all on function private.guard_simulation_station(),private.guard_simulation_inventory(),
  private.guard_demo_lake_source() from public,anon,authenticated,service_role;
commit;
