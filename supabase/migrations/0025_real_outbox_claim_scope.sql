-- Keep real commands separate from simulated dispatch and reject stale device
-- acknowledgements before any acknowledgement, sequence, or outbox mutation.
create or replace function public.record_real_command_acknowledgement(
  p_drone_id uuid, p_command_id uuid, p_sequence bigint, p_plan_id uuid, p_version integer, p_status text, p_detail text
) returns boolean language plpgsql security definer set search_path = '' as $$
declare v_last bigint; v_version integer; v_plan_id uuid; v_acknowledged integer;
begin
  if p_status not in ('accepted','rejected','completed') then return false; end if;
  select last_sequence into v_last from public.drone_credentials where drone_id=p_drone_id and credential_state='active' for update;
  if v_last is null or p_sequence <= v_last then return false; end if;
  select acknowledged_state_version into v_acknowledged from public.drone_inventory where inventory_id=p_drone_id for update;
  if v_acknowledged is null or v_acknowledged > p_version then return false; end if;
  select command.desired_state_version, (command.payload->>'plan_id')::uuid into v_version, v_plan_id
    from public.command_outbox command where command.command_id=p_command_id and command.inventory_id=p_drone_id and command.status='claimed' for update;
  if v_version is null or v_version <> p_version or v_plan_id is distinct from p_plan_id then return false; end if;
  insert into public.command_acknowledgements(drone_id,command_id,sequence,status,detail) values(p_drone_id,p_command_id,p_sequence,p_status,p_detail);
  update public.drone_credentials set last_sequence=p_sequence where drone_id=p_drone_id;
  if p_status in ('accepted','completed') then
    update public.command_outbox set status='acknowledged',claimed_at=null,acknowledged_at=now() where command_id=p_command_id and status='claimed';
    update public.drone_inventory set acknowledged_state_version=p_version where inventory_id=p_drone_id and acknowledged_state_version <= p_version;
  end if;
  return true;
exception when unique_violation then return false;
end; $$;

-- Replace only the command trigger. The shared legacy trigger continues to
-- protect inventory, availability, and assignment rows.
create function private.assert_autonomy_command_ownership()
returns trigger language plpgsql set search_path = '' as $$
declare inventory_station uuid; inventory_lake text; inventory_source text; lake_station uuid; credential_active boolean;
  inventory_lifecycle text; inventory_health text; inventory_connectivity text; inventory_maintenance boolean; inventory_battery integer;
  minimum_battery integer; assignment_plan uuid; assignment_inventory uuid; assignment_version integer; plan_status text;
begin
  select station_id,lake_id,source,lifecycle,health,connectivity,maintenance_due,battery_percent
    into inventory_station,inventory_lake,inventory_source,inventory_lifecycle,inventory_health,inventory_connectivity,inventory_maintenance,inventory_battery
    from public.drone_inventory where inventory_id=new.inventory_id;
  select station_id into lake_station from public.lakes where lake_id=new.lake_id;
  if inventory_station is distinct from new.station_id or inventory_lake is distinct from new.lake_id or lake_station is distinct from new.station_id then
    raise exception 'command inventory must match station lake' using errcode='23514';
  end if;
  if inventory_source = 'simulated' then
    if new.payload ? 'source' and new.payload->>'source' <> 'simulated' then raise exception 'simulated command source mismatch' using errcode='23514'; end if;
    if new.command_type='apply_assignment' then
      select zone_plan_id,inventory_id,desired_state_version into assignment_plan,assignment_inventory,assignment_version from public.zone_assignments where zone_assignment_id=new.zone_assignment_id;
      select status into plan_status from public.zone_plans where zone_plan_id=assignment_plan;
      select minimum_battery_percent into minimum_battery from public.station_fleet_policies where station_id=new.station_id;
      if minimum_battery is null or inventory_lifecycle <> 'circulating' or inventory_health <> 'healthy' or inventory_connectivity <> 'connected'
         or inventory_maintenance or inventory_battery < minimum_battery or assignment_inventory is distinct from new.inventory_id
         or assignment_version is distinct from new.desired_state_version or plan_status <> 'active' then
        raise exception 'apply assignment requires eligible simulated inventory and active assignment' using errcode='23514';
      end if;
    end if;
    return new;
  end if;
  select exists(select 1 from public.drone_credentials where drone_id=new.inventory_id and station_id=new.station_id and credential_state='active') into credential_active;
  if inventory_source <> 'real' or new.payload->>'source' <> 'real' or new.payload->>'transport' <> 'real_gateway' or not credential_active
     or new.command_type not in ('apply_assignment','return_to_reserve','safety_hold') then
    raise exception 'real command requires active credential and gateway transport' using errcode='23514';
  end if;
  if new.command_type='apply_assignment' and (new.payload->>'plan_id' is null or new.payload->>'expires_at' is null) then
    raise exception 'real assignment requires plan and expiry' using errcode='23514';
  end if;
  return new;
end; $$;

drop trigger outbox_station_matches_inputs on public.command_outbox;
create trigger outbox_station_matches_inputs before insert on public.command_outbox for each row execute procedure private.assert_autonomy_command_ownership();

create or replace function public.claim_real_autonomy_outbox(p_station_id uuid, p_lake_id text, p_limit integer default 20)
returns setof public.command_outbox language sql security definer set search_path = '' as $$
  with claimed as (
    select command.command_id from public.command_outbox command
      join public.drone_inventory inventory on inventory.inventory_id=command.inventory_id
      join public.drone_credentials credential on credential.drone_id=inventory.inventory_id and credential.station_id=command.station_id
      where command.station_id = p_station_id and command.lake_id = p_lake_id
        and inventory.source = 'real' and credential.credential_state='active'
        and (command.status='pending' or (command.status='claimed' and command.claimed_at < now() - interval '5 minutes'))
      order by command.created_at,command.command_id for update of command skip locked limit greatest(1,least(p_limit,100))
  ) update public.command_outbox command set status='claimed',claimed_at=now() from claimed where command.command_id=claimed.command_id returning command.*;
$$;

revoke all on function public.record_real_command_acknowledgement(uuid,uuid,bigint,uuid,integer,text,text) from public,anon,authenticated;
revoke all on function public.claim_real_autonomy_outbox(uuid,text,integer) from public,anon,authenticated;
grant execute on function public.record_real_command_acknowledgement(uuid,uuid,bigint,uuid,integer,text,text), public.claim_real_autonomy_outbox(uuid,text,integer) to service_role;
revoke all on function private.assert_autonomy_command_ownership() from public,anon,authenticated;
