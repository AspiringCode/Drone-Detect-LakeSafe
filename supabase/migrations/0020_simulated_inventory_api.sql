-- Service-only mutations behind the authorized simulated-autonomy API.
-- These functions deliberately expose no waypoint, heading, device, or real-fleet control.

create or replace function public.register_simulated_inventory(p_station_id uuid)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_inventory public.drone_inventory%rowtype;
begin
  if not exists (select 1 from public.stations where station_id = p_station_id) then
    return null;
  end if;
  -- The fleet policy must already be explicitly configured.  Its trigger
  -- enforces allowance before this row can be committed.
  insert into public.drone_inventory (station_id, source, lifecycle)
  values (p_station_id, 'simulated', 'available')
  returning * into v_inventory;
  return jsonb_build_object(
    'inventory_id', v_inventory.inventory_id, 'station_id', v_inventory.station_id,
    'lake_id', v_inventory.lake_id, 'source', v_inventory.source,
    'lifecycle', v_inventory.lifecycle,
    'desired_state_version', v_inventory.desired_state_version,
    'acknowledged_state_version', v_inventory.acknowledged_state_version
  );
end;
$$;

create or replace function public.set_simulated_circulation(
  p_station_id uuid, p_inventory_id uuid, p_lake_id text, p_eligible boolean,
  p_reason text, p_actor_user_id uuid, p_reconciliation_id uuid
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_inventory public.drone_inventory%rowtype; v_lake_station uuid; v_prior_state jsonb;
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
    update public.drone_inventory set lake_id = null, lifecycle = 'available'
      where inventory_id = p_inventory_id returning * into v_inventory;
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
    'reconciliation_id', p_reconciliation_id
  );
end;
$$;

revoke all on function public.register_simulated_inventory(uuid) from public, anon, authenticated;
revoke all on function public.set_simulated_circulation(uuid, uuid, text, boolean, text, uuid, uuid) from public, anon, authenticated;
