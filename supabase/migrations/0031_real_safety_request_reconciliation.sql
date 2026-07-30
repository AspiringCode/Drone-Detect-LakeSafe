-- A request ID is the idempotency and reconciliation key for high-impact
-- safety changes.  The same transaction stores both policy and allowed audit.
create unique index if not exists audit_events_allowed_request_action_idx
  on public.audit_events (request_id, action) where decision = 'allowed';

create or replace function private.record_workflow_audit_with_request(
  p_actor_user_id uuid, p_station_id uuid, p_lake_id text, p_request_id uuid,
  p_action text, p_decision text, p_reason text,
  p_prior_state jsonb default null, p_resulting_state jsonb default null
) returns void language sql security definer set search_path = '' as $$
  insert into public.audit_events (
    actor_user_id, station_id, lake_id, request_id, action, decision, reason,
    prior_state, resulting_state, source_context
  ) values (
    p_actor_user_id, p_station_id, p_lake_id, p_request_id, p_action,
    p_decision, p_reason, p_prior_state, p_resulting_state,
    jsonb_build_object('component', 'real_fleet_safety_rpc')
  );
$$;

drop function public.set_real_fleet_autonomy(uuid, text, boolean, text, uuid);
create function public.set_real_fleet_autonomy(
  p_station_id uuid, p_lake_id text, p_enabled boolean, p_reason text,
  p_actor_user_id uuid, p_request_id uuid
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_state text; v_existing jsonb; v_result jsonb;
begin
  if p_request_id is null or length(btrim(coalesce(p_reason,''))) not between 1 and 500 then return null; end if;
  select resulting_state into v_existing from public.audit_events
    where request_id = p_request_id and action = 'real_fleet.autonomy' and decision = 'allowed';
  if found then return v_existing; end if;
  perform private.assert_real_safety_actor(p_station_id,p_actor_user_id);
  if not exists(select 1 from public.lakes where lake_id=p_lake_id and station_id=p_station_id) then return null; end if;
  v_state := case when p_enabled then 'pending_ack' else 'paused' end;
  insert into public.real_fleet_safety_policies(station_id,lake_id,autonomy_state,safe_return_required,updated_by)
    values(p_station_id,p_lake_id,v_state,not p_enabled,p_actor_user_id)
  on conflict(station_id,lake_id) do update set autonomy_state=excluded.autonomy_state,safe_return_required=excluded.safe_return_required,updated_by=excluded.updated_by,updated_at=now();
  v_result := jsonb_build_object('station_id',p_station_id,'lake_id',p_lake_id,'autonomy',v_state,'active_assignments','[]'::jsonb,'pending_assignments','[]'::jsonb,'last_acknowledged_versions','{}'::jsonb);
  perform private.record_workflow_audit_with_request(p_actor_user_id,p_station_id,p_lake_id,p_request_id,'real_fleet.autonomy','allowed',btrim(p_reason),null,v_result);
  return v_result;
end; $$;

drop function public.request_real_fleet_safe_return(uuid, text, text, uuid);
create function public.request_real_fleet_safe_return(
  p_station_id uuid, p_lake_id text, p_reason text, p_actor_user_id uuid,
  p_request_id uuid
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare drone record; v_version integer; v_existing jsonb; v_result jsonb;
begin
  if p_request_id is null or length(btrim(coalesce(p_reason,''))) not between 1 and 500 then return null; end if;
  select resulting_state into v_existing from public.audit_events
    where request_id = p_request_id and action = 'real_fleet.safe_return' and decision = 'allowed';
  if found then return v_existing; end if;
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
  v_result := jsonb_build_object('station_id',p_station_id,'lake_id',p_lake_id,'autonomy','safe_return_requested','active_assignments','[]'::jsonb,'pending_assignments','[]'::jsonb,'last_acknowledged_versions','{}'::jsonb);
  perform private.record_workflow_audit_with_request(p_actor_user_id,p_station_id,p_lake_id,p_request_id,'real_fleet.safe_return','allowed',btrim(p_reason),null,v_result);
  return v_result;
end; $$;

revoke all on function public.set_real_fleet_autonomy(uuid,text,boolean,text,uuid,uuid), public.request_real_fleet_safe_return(uuid,text,text,uuid,uuid) from public, anon, authenticated;
grant execute on function public.set_real_fleet_autonomy(uuid,text,boolean,text,uuid,uuid), public.request_real_fleet_safe_return(uuid,text,text,uuid,uuid) to service_role;
revoke all on function private.record_workflow_audit_with_request(uuid,uuid,text,uuid,text,text,text,jsonb,jsonb) from public, anon, authenticated;
