-- Atomic desired-state commits for autonomous simulated fleet reconciliation.
-- These functions are service-role only; they expose no human steering surface.

create or replace function public.commit_autonomy_reconciliation(
  p_lake_id text,
  p_expected_plan_id uuid,
  p_candidate_plan_id uuid,
  p_assignments jsonb,
  p_commands jsonb
) returns boolean language plpgsql security definer set search_path = '' as $$
declare
  v_station_id uuid;
  v_active_plan_id uuid;
  v_assignment jsonb;
  v_command jsonb;
  v_assignment_id uuid;
begin
  select station_id into v_station_id from public.lakes where lake_id = p_lake_id for update;
  if v_station_id is null then return false; end if;
  select zone_plan_id into v_active_plan_id from public.zone_plans
    where lake_id = p_lake_id and status = 'active' for update;
  if v_active_plan_id is distinct from p_expected_plan_id then return false; end if;
  if not exists (select 1 from public.zone_plans where zone_plan_id = p_candidate_plan_id
                 and lake_id = p_lake_id and station_id = v_station_id and status = 'candidate') then return false; end if;

  update public.zone_plans set status = 'superseded' where zone_plan_id = v_active_plan_id;
  update public.zone_plans set status = 'active' where zone_plan_id = p_candidate_plan_id;

  for v_assignment in select value from jsonb_array_elements(p_assignments) loop
    insert into public.zone_assignments (zone_plan_id, zone_plan_cell_id, inventory_id, station_id, lake_id, desired_state_version)
    values (p_candidate_plan_id, (v_assignment->>'zone_plan_cell_id')::uuid,
            (v_assignment->>'inventory_id')::uuid, v_station_id, p_lake_id,
            (v_assignment->>'desired_state_version')::integer)
    returning zone_assignment_id into v_assignment_id;
    update public.drone_inventory set desired_state_version = (v_assignment->>'desired_state_version')::integer
      where inventory_id = (v_assignment->>'inventory_id')::uuid
        and desired_state_version < (v_assignment->>'desired_state_version')::integer;
  end loop;

  for v_command in select value from jsonb_array_elements(p_commands) loop
    select zone_assignment_id into v_assignment_id from public.zone_assignments
      where zone_plan_id = p_candidate_plan_id
        and inventory_id = (v_command->>'inventory_id')::uuid
        and desired_state_version = (v_command->>'desired_state_version')::integer;
    if (v_command->>'command_type') = 'apply_assignment' and v_assignment_id is null then
      raise exception 'outbox command requires committed assignment' using errcode = '23514';
    end if;
    insert into public.command_outbox (inventory_id, zone_assignment_id, station_id, lake_id, desired_state_version, command_type, payload, idempotency_key)
    values ((v_command->>'inventory_id')::uuid, v_assignment_id,
            v_station_id, p_lake_id, (v_command->>'desired_state_version')::integer,
            v_command->>'command_type', coalesce(v_command->'payload', '{}'::jsonb), v_command->>'idempotency_key')
    on conflict (idempotency_key) do nothing;
  end loop;
  return true;
end;
$$;

create or replace function public.claim_autonomy_outbox(p_limit integer default 20)
returns setof public.command_outbox language sql security definer set search_path = '' as $$
  with claimed as (
    select command_id from public.command_outbox where status = 'pending'
      order by created_at, command_id for update skip locked limit greatest(1, least(p_limit, 100))
  ) update public.command_outbox command set status = 'claimed', claimed_at = now()
    from claimed where command.command_id = claimed.command_id returning command.*;
$$;

create or replace function public.acknowledge_autonomy_command(p_command_id uuid)
returns boolean language plpgsql security definer set search_path = '' as $$
declare v_inventory_id uuid; v_version integer;
begin
  update public.command_outbox set status = 'acknowledged', acknowledged_at = now()
    where command_id = p_command_id and status = 'claimed'
    returning inventory_id, desired_state_version into v_inventory_id, v_version;
  if v_inventory_id is null then return false; end if;
  update public.drone_inventory set acknowledged_state_version = greatest(acknowledged_state_version, v_version)
    where inventory_id = v_inventory_id;
  return true;
end;
$$;

create or replace function public.release_autonomy_command(p_command_id uuid)
returns boolean language plpgsql security definer set search_path = '' as $$
begin
  update public.command_outbox set status = 'pending', claimed_at = null
    where command_id = p_command_id and status = 'claimed';
  return found;
end;
$$;

revoke all on function public.commit_autonomy_reconciliation(text, uuid, uuid, jsonb, jsonb) from public, anon, authenticated;
revoke all on function public.claim_autonomy_outbox(integer) from public, anon, authenticated;
revoke all on function public.acknowledge_autonomy_command(uuid) from public, anon, authenticated;
revoke all on function public.release_autonomy_command(uuid) from public, anon, authenticated;
