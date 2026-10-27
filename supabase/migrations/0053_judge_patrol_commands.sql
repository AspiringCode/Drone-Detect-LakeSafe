-- Permit reviewed patrol uploads within opted-in judge stations only.
begin;
create or replace function public.queue_real_patrol(p_station_id uuid,p_drone_id uuid,p_lake_id text,p_actor uuid,p_payload jsonb)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare inventory public.drone_inventory%rowtype; credential public.drone_credentials%rowtype; command public.real_patrol_commands%rowtype;
begin
  if exists (
    select 1 from public.station_memberships m join public.station_membership_roles r using(membership_id)
    where m.station_id=p_station_id and m.user_id=p_actor and r.role='demo_operator'
  ) then
    perform private.assert_real_safety_actor(p_station_id,p_actor);
  end if;
  if not exists (
    select 1 from public.station_memberships membership
    join public.station_membership_roles role on role.membership_id=membership.membership_id
    join public.officer_verifications verification on verification.user_id=membership.user_id
    where membership.station_id=p_station_id and membership.user_id=p_actor and membership.status='active'
      and role.role in ('station_admin','demo_operator') and verification.status='verified' and verification.revoked_at is null
      and (verification.expires_at is null or verification.expires_at>now())
  ) then return null; end if;
  select * into credential from public.drone_credentials where drone_id=p_drone_id for update;
  select * into inventory from public.drone_inventory where inventory_id=p_drone_id for update;
  if inventory.station_id is distinct from p_station_id or inventory.lake_id is distinct from p_lake_id
    or inventory.source is distinct from 'real' or inventory.lifecycle='retired'
    or credential.credential_state is distinct from 'active' or credential.station_id is distinct from p_station_id
    or p_payload->>'lake_id' is distinct from p_lake_id or p_payload->>'drone_id' is distinct from p_drone_id::text
    or jsonb_typeof(p_payload->'mission') is distinct from 'array'
    or not coalesce((p_payload->>'mission_hash') ~ '^[0-9a-f]{64}$',false)
    then return null; end if;
  perform private.refresh_real_patrols(p_drone_id);
  if exists(select 1 from public.real_patrol_commands where drone_id=p_drone_id and status in ('queued','delivered')) then return null; end if;
  insert into public.real_patrol_commands(drone_id,station_id,lake_id,credential_id,created_by,payload)
    values(p_drone_id,p_station_id,p_lake_id,credential.credential_id,p_actor,p_payload) returning * into command;
  perform private.record_workflow_audit(p_actor,p_station_id,p_lake_id,'patrol.queue','allowed','reviewed mission queued',null,
    jsonb_build_object('command_id',command.command_id,'mission_hash',p_payload->>'mission_hash'));
  return jsonb_build_object('command_id',command.command_id,'status',command.status,'expires_at',command.expires_at);
end; $$;
commit;
