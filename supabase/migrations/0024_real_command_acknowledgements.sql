-- Device acknowledgements are durable, append-only, and advance only after an
-- exact command/credential/sequence match. Service role only.
create or replace function public.record_real_command_acknowledgement(
  p_drone_id uuid, p_command_id uuid, p_sequence bigint, p_plan_id uuid, p_version integer, p_status text, p_detail text
) returns boolean language plpgsql security definer set search_path = '' as $$
declare v_last bigint; v_version integer; v_plan_id uuid;
begin
  if p_status not in ('accepted','rejected','completed') then return false; end if;
  select last_sequence into v_last from public.drone_credentials where drone_id=p_drone_id and credential_state='active' for update;
  if v_last is null or p_sequence <= v_last then return false; end if;
  select command.desired_state_version, (command.payload->>'plan_id')::uuid into v_version, v_plan_id
    from public.command_outbox command where command.command_id=p_command_id and command.inventory_id=p_drone_id and command.status='claimed' for update;
  if v_version is null or v_version <> p_version or v_plan_id is distinct from p_plan_id then return false; end if;
  insert into public.command_acknowledgements(drone_id,command_id,sequence,status,detail) values(p_drone_id,p_command_id,p_sequence,p_status,p_detail);
  update public.drone_credentials set last_sequence=p_sequence where drone_id=p_drone_id;
  if p_status in ('accepted','completed') then
    update public.command_outbox set status='acknowledged',claimed_at=null,acknowledged_at=now() where command_id=p_command_id and status='claimed';
    update public.drone_inventory set acknowledged_state_version=greatest(acknowledged_state_version,p_version) where inventory_id=p_drone_id and acknowledged_state_version <= p_version;
  end if;
  return true;
exception when unique_violation then return false;
end; $$;

create or replace function public.advance_real_command_acknowledgement(
  p_drone_id uuid, p_command_id uuid, p_version integer
) returns boolean language plpgsql security definer set search_path = '' as $$
declare v_version integer;
begin
  select desired_state_version into v_version from public.command_outbox where command_id=p_command_id and inventory_id=p_drone_id and status='claimed' for update;
  if v_version is null or v_version <> p_version then return false; end if;
  update public.command_outbox set status='acknowledged',claimed_at=null,acknowledged_at=now() where command_id=p_command_id and status='claimed';
  update public.drone_inventory set acknowledged_state_version=greatest(acknowledged_state_version,p_version) where inventory_id=p_drone_id and acknowledged_state_version <= p_version;
  return true;
end; $$;

revoke all on function public.record_real_command_acknowledgement(uuid,uuid,bigint,uuid,integer,text,text) from public,anon,authenticated;
revoke all on function public.advance_real_command_acknowledgement(uuid,uuid,integer) from public,anon,authenticated;
grant execute on function public.record_real_command_acknowledgement(uuid,uuid,bigint,uuid,integer,text,text), public.advance_real_command_acknowledgement(uuid,uuid,integer) to service_role;
