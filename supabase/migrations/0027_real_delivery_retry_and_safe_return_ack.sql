-- Real delivery is leased with bounded backoff. Expired intent is never
-- silently reclaimed or represented as active capacity.

create or replace function public.record_real_command_acknowledgement(
  p_drone_id uuid, p_command_id uuid, p_sequence bigint, p_plan_id uuid, p_version integer, p_status text, p_detail text
) returns boolean language plpgsql security definer set search_path = '' as $$
declare v_last bigint; v_version integer; v_plan_id uuid; v_acknowledged integer; v_type text;
begin
  if p_status not in ('accepted','rejected','completed') then return false; end if;
  select last_sequence into v_last from public.drone_credentials where drone_id=p_drone_id and credential_state='active' for update;
  if v_last is null or p_sequence <= v_last then return false; end if;
  select acknowledged_state_version into v_acknowledged from public.drone_inventory where inventory_id=p_drone_id for update;
  if v_acknowledged is null or v_acknowledged > p_version then return false; end if;
  select command.desired_state_version, (command.payload->>'plan_id')::uuid, command.command_type
    into v_version, v_plan_id, v_type
    from public.command_outbox command where command.command_id=p_command_id and command.inventory_id=p_drone_id and command.status='claimed' for update;
  if v_version is null or v_version <> p_version then return false; end if;
  if v_type = 'apply_assignment' and v_plan_id is distinct from p_plan_id then return false; end if;
  if v_type in ('return_to_reserve','safety_hold') and (v_plan_id is not null or p_plan_id is not null) then return false; end if;
  if v_type not in ('apply_assignment','return_to_reserve','safety_hold') then return false; end if;
  insert into public.command_acknowledgements(drone_id,command_id,sequence,status,detail) values(p_drone_id,p_command_id,p_sequence,p_status,p_detail);
  update public.drone_credentials set last_sequence=p_sequence where drone_id=p_drone_id;
  if p_status in ('accepted','completed') then
    update public.command_outbox set status='acknowledged',claimed_at=null,acknowledged_at=now() where command_id=p_command_id and status='claimed';
    update public.drone_inventory set acknowledged_state_version=p_version where inventory_id=p_drone_id and acknowledged_state_version <= p_version;
  end if;
  return true;
exception when unique_violation then return false;
end; $$;

create or replace function public.claim_real_autonomy_outbox(p_station_id uuid, p_lake_id text, p_limit integer default 20)
returns setof public.command_outbox language sql security definer set search_path = '' as $$
  with claimed as (
    select command.command_id from public.command_outbox command
      join public.drone_inventory inventory on inventory.inventory_id=command.inventory_id
      join public.drone_credentials credential on credential.drone_id=inventory.inventory_id and credential.station_id=command.station_id
      where command.station_id = p_station_id and command.lake_id = p_lake_id
        and inventory.station_id = command.station_id and inventory.lake_id = command.lake_id
        and inventory.source = 'real' and credential.credential_state='active'
        and command.status='pending'
        and (command.expires_at is null or command.expires_at > now())
        and (command.next_attempt_at is null or command.next_attempt_at <= now())
      order by command.created_at,command.command_id for update of command skip locked limit greatest(1,least(p_limit,100))
  ) update public.command_outbox command
    set status='claimed',claimed_at=now(),delivery_attempts=command.delivery_attempts+1,next_attempt_at=null
    from claimed where command.command_id=claimed.command_id returning command.*;
$$;

create or replace function public.release_real_autonomy_command(p_command_id uuid, p_max_attempts integer default 3)
returns boolean language plpgsql security definer set search_path = '' as $$
begin
  update public.command_outbox command
    set status=case when command.delivery_attempts >= greatest(1,p_max_attempts)
                          or (command.expires_at is not null and command.expires_at <= now()) then 'failed' else 'pending' end,
        claimed_at=null,
        next_attempt_at=case when command.delivery_attempts >= greatest(1,p_max_attempts)
                          or (command.expires_at is not null and command.expires_at <= now()) then null
                     else now() + make_interval(secs => (2 ^ least(command.delivery_attempts, 8))::integer) end
   where command.command_id=p_command_id and command.status='claimed' and command.payload->>'source'='real';
  return found;
end; $$;

create or replace function public.expire_real_command_delivery(p_station_id uuid,p_lake_id text,p_max_attempts integer default 3)
returns setof text language sql security definer set search_path = '' as $$
  update public.command_outbox command set status='failed',claimed_at=null,next_attempt_at=null
   where command.station_id=p_station_id and command.lake_id=p_lake_id
     and command.payload->>'source'='real' and command.status in ('pending','claimed')
     and (command.delivery_attempts >= greatest(1,p_max_attempts) or (command.expires_at is not null and command.expires_at <= now()))
   returning command.inventory_id::text;
$$;

revoke all on function public.record_real_command_acknowledgement(uuid,uuid,bigint,uuid,integer,text,text),public.claim_real_autonomy_outbox(uuid,text,integer),public.release_real_autonomy_command(uuid,integer),public.expire_real_command_delivery(uuid,text,integer) from public,anon,authenticated;
grant execute on function public.record_real_command_acknowledgement(uuid,uuid,bigint,uuid,integer,text,text),public.claim_real_autonomy_outbox(uuid,text,integer),public.release_real_autonomy_command(uuid,integer),public.expire_real_command_delivery(uuid,text,integer) to service_role;
