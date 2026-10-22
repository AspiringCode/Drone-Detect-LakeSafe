-- Durable real-fleet safety policy.  These functions accept policy intent only;
-- they never accept coordinates, headings, waypoints, or manual flight input.

create table public.real_fleet_safety_policies (
  station_id uuid not null references public.stations(station_id) on delete restrict,
  lake_id text not null references public.lakes(lake_id) on delete restrict,
  autonomy_state text not null default 'paused' check (autonomy_state in ('paused','pending_ack','active','degraded','safe_return_requested','gateway_unavailable')),
  safe_return_required boolean not null default false,
  updated_by uuid not null references auth.users(id) on delete restrict,
  updated_at timestamptz not null default now(),
  primary key (station_id, lake_id)
);

alter table public.command_outbox add column if not exists delivery_attempts integer not null default 0 check (delivery_attempts >= 0);
alter table public.command_outbox add column if not exists next_attempt_at timestamptz;
alter table public.command_outbox add column if not exists expires_at timestamptz;

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

create or replace function public.set_real_fleet_autonomy(
  p_station_id uuid, p_lake_id text, p_enabled boolean, p_reason text, p_actor_user_id uuid
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_state text;
begin
  if length(btrim(coalesce(p_reason,''))) not between 1 and 500 then return null; end if;
  perform private.assert_real_safety_actor(p_station_id,p_actor_user_id);
  if not exists(select 1 from public.lakes where lake_id=p_lake_id and station_id=p_station_id) then return null; end if;
  v_state := case when p_enabled then 'pending_ack' else 'paused' end;
  insert into public.real_fleet_safety_policies(station_id,lake_id,autonomy_state,safe_return_required,updated_by)
    values(p_station_id,p_lake_id,v_state,not p_enabled,p_actor_user_id)
  on conflict(station_id,lake_id) do update set autonomy_state=excluded.autonomy_state,safe_return_required=excluded.safe_return_required,updated_by=excluded.updated_by,updated_at=now();
  perform private.record_workflow_audit(p_actor_user_id,p_station_id,p_lake_id,'real_fleet.autonomy','allowed',btrim(p_reason),null,jsonb_build_object('autonomy',v_state,'source','real'));
  return jsonb_build_object('station_id',p_station_id,'lake_id',p_lake_id,'autonomy',v_state,'active_assignments','[]'::jsonb,'pending_assignments','[]'::jsonb,'last_acknowledged_versions','{}'::jsonb);
end; $$;

create or replace function public.request_real_fleet_safe_return(
  p_station_id uuid, p_lake_id text, p_reason text, p_actor_user_id uuid
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare drone record; v_version integer;
begin
  if length(btrim(coalesce(p_reason,''))) not between 1 and 500 then return null; end if;
  perform private.assert_real_safety_actor(p_station_id,p_actor_user_id);
  if not exists(select 1 from public.lakes where lake_id=p_lake_id and station_id=p_station_id) then return null; end if;
  insert into public.real_fleet_safety_policies(station_id,lake_id,autonomy_state,safe_return_required,updated_by)
    values(p_station_id,p_lake_id,'safe_return_requested',true,p_actor_user_id)
  on conflict(station_id,lake_id) do update set autonomy_state='safe_return_requested',safe_return_required=true,updated_by=excluded.updated_by,updated_at=now();
  for drone in select inventory_id,desired_state_version from public.drone_inventory where station_id=p_station_id and lake_id=p_lake_id and source='real' and lifecycle='circulating' loop
    v_version := drone.desired_state_version + 1;
    update public.drone_inventory set desired_state_version=v_version where inventory_id=drone.inventory_id;
    insert into public.command_outbox(inventory_id,station_id,lake_id,desired_state_version,command_type,payload,idempotency_key,expires_at)
      values(drone.inventory_id,p_station_id,p_lake_id,v_version,'return_to_reserve',jsonb_build_object('source','real','transport','real_gateway','reason',btrim(p_reason),'expires_at',(now()+interval '5 minutes')::text),encode(extensions.digest(convert_to('safe-return:'||drone.inventory_id||':'||v_version,'utf8'),'sha256'),'hex'),now()+interval '5 minutes')
    on conflict(idempotency_key) do nothing;
  end loop;
  perform private.record_workflow_audit(p_actor_user_id,p_station_id,p_lake_id,'real_fleet.safe_return','allowed',btrim(p_reason),null,jsonb_build_object('autonomy','safe_return_requested','source','real'));
  return jsonb_build_object('station_id',p_station_id,'lake_id',p_lake_id,'autonomy','safe_return_requested','active_assignments','[]'::jsonb,'pending_assignments','[]'::jsonb,'last_acknowledged_versions','{}'::jsonb);
end; $$;

-- A bounded delivery worker may retry only unexpired real commands.  Expired
-- commands become failed; acknowledged_state_version is deliberately untouched.
create or replace function public.expire_real_command_delivery(p_station_id uuid,p_lake_id text,p_max_attempts integer default 3)
returns setof text language sql security definer set search_path = '' as $$
  update public.command_outbox command set status='failed',claimed_at=null,next_attempt_at=null
   where command.station_id=p_station_id and command.lake_id=p_lake_id
     and command.payload->>'source'='real' and command.status in ('pending','claimed')
     and (command.delivery_attempts >= greatest(1,p_max_attempts) or (command.expires_at is not null and command.expires_at <= now()))
   returning command.inventory_id::text;
$$;

alter table public.real_fleet_safety_policies enable row level security;
alter table public.real_fleet_safety_policies force row level security;
revoke all on public.real_fleet_safety_policies from public,anon,authenticated;
revoke all on function public.set_real_fleet_autonomy(uuid,text,boolean,text,uuid),public.request_real_fleet_safe_return(uuid,text,text,uuid),public.expire_real_command_delivery(uuid,text,integer) from public,anon,authenticated;
grant execute on function public.set_real_fleet_autonomy(uuid,text,boolean,text,uuid),public.request_real_fleet_safe_return(uuid,text,text,uuid),public.expire_real_command_delivery(uuid,text,integer) to service_role;
revoke all on function private.assert_real_safety_actor(uuid,uuid) from public,anon,authenticated;
