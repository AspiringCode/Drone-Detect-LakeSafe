-- Retire only the separate judge fixtures and preserve their operational history.
begin;
do $guard$
begin
 if exists(select 1 from public.drone_inventory where station_id in ('9f96a25d-bb1a-5b4c-84b4-e25bf2f5c284','eb0e4812-2585-5411-a1a5-ea5033915820','748a2fb4-6356-5936-b016-2325bbe96d69') and source='real' and lifecycle<>'retired') then
  raise exception 'Judge station has an unretired device; review before removing its setup';
 end if;
 if exists(select 1 from public.lakes where station_id in ('9f96a25d-bb1a-5b4c-84b4-e25bf2f5c284','eb0e4812-2585-5411-a1a5-ea5033915820','748a2fb4-6356-5936-b016-2325bbe96d69') and lake_id not in ('judge-lake-beaver','judge-lake-sammamish','judge-lake-pine')) then
  raise exception 'Judge station contains an unexpected lake';
 end if;
end;
$guard$;
update public.stations set status='suspended',public_pages_open=false,demo_device_access=false,updated_at=now()
 where station_id in ('9f96a25d-bb1a-5b4c-84b4-e25bf2f5c284','eb0e4812-2585-5411-a1a5-ea5033915820','748a2fb4-6356-5936-b016-2325bbe96d69');
update public.station_memberships set status='revoked',updated_at=now()
 where station_id in ('9f96a25d-bb1a-5b4c-84b4-e25bf2f5c284','eb0e4812-2585-5411-a1a5-ea5033915820','748a2fb4-6356-5936-b016-2325bbe96d69');
-- These three administrative anchor memberships were created solely for the discarded fixtures.
delete from public.station_memberships where station_id in ('9f96a25d-bb1a-5b4c-84b4-e25bf2f5c284','eb0e4812-2585-5411-a1a5-ea5033915820','748a2fb4-6356-5936-b016-2325bbe96d69') and user_id='44e8b14d-db3d-4d08-ad4d-3cceac1a8521';
update public.cac_judge_access set expires_at=created_at+interval '1 second'
 where user_id in (select id from auth.users where email in ('judge_all@lakesafe.example.test','judge_ls@lakesafe.example.test','judge_bl@lakesafe.example.test','judge_pl@lakesafe.example.test')
 and raw_app_meta_data @> '{"public_simulation_only":true}'::jsonb);
update public.officer_verifications set status='revoked',revoked_at=coalesce(revoked_at,now())
 where user_id in (select id from auth.users where email in ('judge_all@lakesafe.example.test','judge_ls@lakesafe.example.test','judge_bl@lakesafe.example.test','judge_pl@lakesafe.example.test')
 and raw_app_meta_data @> '{"public_simulation_only":true}'::jsonb);
update auth.users set banned_until=timestamptz '2100-01-01 00:00:00+00'
 where email in ('judge_all@lakesafe.example.test','judge_ls@lakesafe.example.test','judge_bl@lakesafe.example.test','judge_pl@lakesafe.example.test')
 and raw_app_meta_data @> '{"public_simulation_only":true}'::jsonb;
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
create or replace function private.assert_real_safety_actor(p_station_id uuid, p_actor_user_id uuid)
returns void language plpgsql security definer set search_path = '' as $$
begin
  if not exists (
    select 1 from public.station_memberships membership
    join public.station_membership_roles membership_role on membership_role.membership_id=membership.membership_id
    join public.officer_verifications verification on verification.user_id=membership.user_id
    where membership.station_id=p_station_id and membership.user_id=p_actor_user_id
      and membership.status='active' and membership_role.role='safety_supervisor'
      and private.officer_verification_is_current(verification.verification_id)
  ) then raise exception 'verified safety supervisor required' using errcode='42501'; end if;
end; $$;
create or replace function public.queue_real_patrol(p_station_id uuid,p_drone_id uuid,p_lake_id text,p_actor uuid,p_payload jsonb)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare inventory public.drone_inventory%rowtype; credential public.drone_credentials%rowtype; command public.real_patrol_commands%rowtype;
begin
  if not exists (
    select 1 from public.station_memberships membership
    join public.station_membership_roles role on role.membership_id=membership.membership_id
    join public.officer_verifications verification on verification.user_id=membership.user_id
    where membership.station_id=p_station_id and membership.user_id=p_actor and membership.status='active'
      and role.role='station_admin' and verification.status='verified' and verification.revoked_at is null
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
set constraints all immediate;
commit;
