-- Service-only mutations behind the authorized simulated-autonomy API.
-- These functions deliberately expose no waypoint, heading, device, or real-fleet control.

drop function if exists public.register_simulated_inventory(uuid);
drop function if exists public.set_simulated_circulation(uuid, uuid, text, boolean, text, uuid, uuid);

create function public.register_simulated_inventory(p_station_id uuid, p_count integer)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_inventory public.drone_inventory%rowtype; v_allowance integer; v_existing integer;
  v_items jsonb := '[]'::jsonb; v_index integer;
begin
  if p_count not between 1 and 100 then
    raise exception 'simulated inventory count is invalid' using errcode = '23514';
  end if;
  select simulated_inventory_allowance into v_allowance from public.station_fleet_policies
    where station_id = p_station_id for update;
  if v_allowance is null then raise exception 'station fleet policy is required' using errcode = '23514'; end if;
  select count(*) into v_existing from public.drone_inventory
    where station_id = p_station_id and source = 'simulated';
  if v_existing + p_count > v_allowance then
    raise exception 'simulated inventory allowance exceeded' using errcode = '23514';
  end if;
  for v_index in 1..p_count loop
    insert into public.drone_inventory (station_id, source, lifecycle)
    values (p_station_id, 'simulated', 'available') returning * into v_inventory;
    v_items := v_items || jsonb_build_array(jsonb_build_object(
      'inventory_id', v_inventory.inventory_id, 'station_id', v_inventory.station_id,
      'lake_id', v_inventory.lake_id, 'source', v_inventory.source,
      'lifecycle', v_inventory.lifecycle, 'desired_state_version', v_inventory.desired_state_version,
      'acknowledged_state_version', v_inventory.acknowledged_state_version));
  end loop;
  return v_items;
end;
$$;

create function public.request_simulated_circulation(
  p_station_id uuid, p_inventory_id uuid, p_lake_id text, p_eligible boolean,
  p_reason text, p_actor_user_id uuid, p_reconciliation_id uuid
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_inventory public.drone_inventory%rowtype; v_lake_station uuid; v_prior_state jsonb;
  v_next_version integer; v_command_key text;
begin
  if length(trim(p_reason)) not between 1 and 500 then
    raise exception 'a circulation reason is required' using errcode = '23514';
  end if;
  select * into v_inventory from public.drone_inventory
    where inventory_id = p_inventory_id and station_id = p_station_id for update;
  select station_id into v_lake_station from public.lakes where lake_id = p_lake_id;
  if v_inventory.inventory_id is null or v_inventory.source <> 'simulated' or v_lake_station is distinct from p_station_id then
    return null;
  end if;
  v_prior_state := jsonb_build_object('lake_id', v_inventory.lake_id, 'lifecycle', v_inventory.lifecycle,
    'source', v_inventory.source, 'desired_state_version', v_inventory.desired_state_version,
    'acknowledged_state_version', v_inventory.acknowledged_state_version);

  if p_eligible then
    update public.drone_inventory set lake_id = p_lake_id, lifecycle = 'circulating'
      where inventory_id = p_inventory_id returning * into v_inventory;
    insert into public.drone_availability_requests (inventory_id, station_id, lake_id, eligible, reason, requested_by)
      values (p_inventory_id, p_station_id, p_lake_id, true, trim(p_reason), p_actor_user_id);
  else
    if v_inventory.lake_id is distinct from p_lake_id then return null; end if;
    v_next_version := v_inventory.desired_state_version + 1;
    v_command_key := p_reconciliation_id::text || ':return_to_reserve:' || p_inventory_id::text;
    -- Queue the safe desired state before releasing lake ownership.  This is
    -- one transaction: either the return command and new version both exist,
    -- or the drone remains circulating with its prior desired state.
    insert into public.command_outbox (
      inventory_id, station_id, lake_id, desired_state_version, command_type,
      payload, idempotency_key
    ) values (
      p_inventory_id, p_station_id, p_lake_id, v_next_version, 'return_to_reserve',
      jsonb_build_object('reconciliation_id', p_reconciliation_id), v_command_key
    );
    update public.drone_inventory set lake_id = null, lifecycle = 'available',
      desired_state_version = v_next_version where inventory_id = p_inventory_id returning * into v_inventory;
  end if;

  insert into public.audit_events (
    actor_user_id, station_id, lake_id, request_id, action, decision, reason,
    prior_state, resulting_state, source_context
  ) values (
    p_actor_user_id, p_station_id, p_lake_id, p_reconciliation_id,
    'simulated_circulation_changed', 'allowed', trim(p_reason),
    v_prior_state,
    jsonb_build_object('inventory_id', v_inventory.inventory_id, 'lake_id', v_inventory.lake_id,
      'lifecycle', v_inventory.lifecycle, 'desired_state_version', v_inventory.desired_state_version,
      'acknowledged_state_version', v_inventory.acknowledged_state_version),
    jsonb_build_object('component', 'simulated_autonomy_api', 'reconciliation_id', p_reconciliation_id)
  );
  return jsonb_build_object(
    'inventory_id', v_inventory.inventory_id, 'station_id', v_inventory.station_id,
    'lake_id', v_inventory.lake_id, 'source', v_inventory.source,
    'lifecycle', v_inventory.lifecycle,
    'desired_state_version', v_inventory.desired_state_version,
    'acknowledged_state_version', v_inventory.acknowledged_state_version,
    'pending_command_type', case when p_eligible then null else 'return_to_reserve' end,
    'reconciliation_id', p_reconciliation_id
  );
end;
$$;

revoke all on function public.register_simulated_inventory(uuid, integer) from public, anon, authenticated;
revoke all on function public.request_simulated_circulation(uuid, uuid, text, boolean, text, uuid, uuid) from public, anon, authenticated;
