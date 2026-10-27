-- Device demonstrations are opt-in and remain isolated from ordinary stations.
begin;
alter table public.stations add column demo_device_access boolean not null default false
  check (not demo_device_access or simulation_only);

create or replace function private.guard_simulation_station() returns trigger
language plpgsql set search_path='' as $$
begin
  if old.simulation_only and not new.simulation_only then
    raise exception 'demo stations cannot become ordinary stations' using errcode='23514';
  end if;
  if new.simulation_only and not new.demo_device_access and exists (
    select 1 from public.drone_inventory where station_id=new.station_id and source='real'
  ) then
    raise exception 'simulation station cannot contain real devices without device access' using errcode='23514';
  end if;
  return new;
end; $$;

create or replace function private.guard_simulation_inventory() returns trigger
language plpgsql set search_path='' as $$
begin
  if new.source='real' and exists (
    select 1 from public.stations where station_id=new.station_id
      and simulation_only and not demo_device_access
  ) then
    raise exception 'real devices require explicit demo station device access' using errcode='23514';
  end if;
  return new;
end; $$;

create or replace function private.assert_real_safety_actor(p_station_id uuid, p_actor_user_id uuid)
returns void language plpgsql security definer set search_path='' as $$
begin
  if not exists (
    select 1 from public.station_memberships membership
    join public.stations station on station.station_id=membership.station_id
    join public.station_membership_roles membership_role on membership_role.membership_id=membership.membership_id
    join public.officer_verifications verification on verification.user_id=membership.user_id
    where membership.station_id=p_station_id and membership.user_id=p_actor_user_id
      and membership.status='active' and membership_role.role='safety_supervisor'
      and private.officer_verification_is_current(verification.verification_id)
      and (not exists (
        select 1 from public.station_membership_roles r
        where r.membership_id=membership.membership_id and r.role='demo_operator'
      ) or (station.simulation_only and station.demo_device_access and exists (
        select 1 from public.cac_judge_access access
        where access.user_id=p_actor_user_id and access.expires_at>now()
      )))
  ) then raise exception 'verified station safety supervisor required' using errcode='42501'; end if;
end; $$;
commit;
