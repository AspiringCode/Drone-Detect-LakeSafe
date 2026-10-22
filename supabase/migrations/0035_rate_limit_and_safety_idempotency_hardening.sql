-- Serialize first claims as well as updates.  Without this lock two API
-- workers can both observe an absent bucket and one receives a unique-key
-- failure instead of the deterministic allow/deny result.
create or replace function public.claim_rate_limit(
  p_scope text, p_subject text, p_limit integer, p_window_seconds integer
) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  bucket public.privileged_rate_limit_buckets%rowtype;
  now_at timestamptz := clock_timestamp();
  remaining integer;
begin
  if length(btrim(coalesce(p_scope, ''))) = 0
     or length(btrim(coalesce(p_subject, ''))) = 0
     or p_limit < 1 or p_limit > 10000
     or p_window_seconds < 1 or p_window_seconds > 86400 then
    raise exception 'invalid rate-limit claim' using errcode = '22023';
  end if;

  perform pg_advisory_xact_lock(hashtextextended(jsonb_build_array(p_scope, p_subject)::text, 0));
  select * into bucket from public.privileged_rate_limit_buckets
    where scope = p_scope and subject = p_subject for update;
  if not found then
    insert into public.privileged_rate_limit_buckets(scope, subject, window_started_at, request_count)
      values (p_scope, p_subject, now_at, 1);
    return jsonb_build_object('allowed', true, 'retry_after_seconds', 0);
  end if;

  if bucket.window_started_at + make_interval(secs => p_window_seconds) <= now_at then
    update public.privileged_rate_limit_buckets
      set window_started_at = now_at, request_count = 1, updated_at = now_at
      where scope = p_scope and subject = p_subject;
    return jsonb_build_object('allowed', true, 'retry_after_seconds', 0);
  end if;
  if bucket.request_count < p_limit then
    update public.privileged_rate_limit_buckets
      set request_count = request_count + 1, updated_at = now_at
      where scope = p_scope and subject = p_subject;
    return jsonb_build_object('allowed', true, 'retry_after_seconds', 0);
  end if;
  remaining := greatest(1, ceil(extract(epoch from (bucket.window_started_at + make_interval(secs => p_window_seconds) - now_at)))::integer);
  return jsonb_build_object('allowed', false, 'retry_after_seconds', remaining);
end;
$$;

-- Request IDs are client-correlatable, not authorization credentials.  Scope
-- idempotency to the same actor and exact operational resource before reuse.
drop index if exists public.audit_events_allowed_request_action_idx;
create unique index audit_events_allowed_request_actor_resource_idx
  on public.audit_events (request_id, action, actor_user_id, station_id, lake_id)
  where decision = 'allowed';

create or replace function public.set_real_fleet_autonomy(
  p_station_id uuid, p_lake_id text, p_enabled boolean, p_reason text,
  p_actor_user_id uuid, p_request_id uuid
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_state text; v_existing jsonb; v_result jsonb;
begin
  if p_request_id is null or length(btrim(coalesce(p_reason,''))) not between 1 and 500 then return null; end if;
  perform private.assert_real_safety_actor(p_station_id,p_actor_user_id);
  if not exists(select 1 from public.lakes where lake_id=p_lake_id and station_id=p_station_id) then return null; end if;
  select resulting_state into v_existing from public.audit_events
    where request_id = p_request_id and action = 'real_fleet.autonomy' and decision = 'allowed'
      and actor_user_id = p_actor_user_id and station_id = p_station_id and lake_id = p_lake_id;
  if found then return v_existing; end if;
  v_state := case when p_enabled then 'pending_ack' else 'paused' end;
  insert into public.real_fleet_safety_policies(station_id,lake_id,autonomy_state,safe_return_required,updated_by)
    values(p_station_id,p_lake_id,v_state,not p_enabled,p_actor_user_id)
  on conflict(station_id,lake_id) do update set autonomy_state=excluded.autonomy_state,safe_return_required=excluded.safe_return_required,updated_by=excluded.updated_by,updated_at=now();
  v_result := jsonb_build_object('station_id',p_station_id,'lake_id',p_lake_id,'autonomy',v_state,'active_assignments','[]'::jsonb,'pending_assignments','[]'::jsonb,'last_acknowledged_versions','{}'::jsonb);
  perform private.record_workflow_audit_with_request(p_actor_user_id,p_station_id,p_lake_id,p_request_id,'real_fleet.autonomy','allowed',btrim(p_reason),null,v_result);
  return v_result;
end; $$;

create or replace function public.request_real_fleet_safe_return(
  p_station_id uuid, p_lake_id text, p_reason text, p_actor_user_id uuid,
  p_request_id uuid
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare drone record; v_version integer; v_existing jsonb; v_result jsonb;
begin
  if p_request_id is null or length(btrim(coalesce(p_reason,''))) not between 1 and 500 then return null; end if;
  perform private.assert_real_safety_actor(p_station_id,p_actor_user_id);
  if not exists(select 1 from public.lakes where lake_id=p_lake_id and station_id=p_station_id) then return null; end if;
  select resulting_state into v_existing from public.audit_events
    where request_id = p_request_id and action = 'real_fleet.safe_return' and decision = 'allowed'
      and actor_user_id = p_actor_user_id and station_id = p_station_id and lake_id = p_lake_id;
  if found then return v_existing; end if;
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
