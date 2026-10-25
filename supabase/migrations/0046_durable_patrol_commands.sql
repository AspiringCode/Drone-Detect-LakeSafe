-- Durable reviewed mission uploads. Disable queue/delivery first when rolling back;
-- retain this table and its audit history while outstanding commands expire.
create table public.real_patrol_commands (
  command_id uuid primary key default gen_random_uuid(),
  drone_id uuid not null references public.drone_inventory(inventory_id) on delete restrict,
  station_id uuid not null references public.stations(station_id) on delete restrict,
  lake_id text not null references public.lakes(lake_id) on delete restrict,
  credential_id uuid not null references public.drone_credentials(credential_id) on delete restrict,
  created_by uuid not null references auth.users(id) on delete restrict,
  payload jsonb not null,
  status text not null default 'queued' check (status in ('queued','delivered','uploaded','rejected','expired')),
  detail text,
  created_at timestamptz not null default now(),
  delivered_at timestamptz,
  acknowledged_at timestamptz,
  acknowledgement_sequence bigint,
  expires_at timestamptz not null default (now() + interval '120 seconds'),
  check (expires_at > created_at),
  check (coalesce(jsonb_typeof(payload->'mission') = 'array',false)),
  check (jsonb_array_length(payload->'mission') >= 3),
  check (coalesce((payload->>'mission_hash') ~ '^[0-9a-f]{64}$',false))
);
create index real_patrol_commands_drone_status on public.real_patrol_commands(drone_id,status);
alter table public.real_patrol_commands enable row level security;
alter table public.real_patrol_commands force row level security;
revoke all on public.real_patrol_commands from public,anon,authenticated;
grant select on public.real_patrol_commands to service_role;

create function private.refresh_real_patrols(p_drone_id uuid)
returns void language plpgsql set search_path = '' as $$
begin
  update public.real_patrol_commands command set status='expired',detail='Mission upload deadline expired'
    where drone_id=p_drone_id and status in ('queued','delivered') and expires_at<=now();
  update public.real_patrol_commands command set status='rejected',detail='Drone assignment or credential changed'
    where command.drone_id=p_drone_id and command.status in ('queued','delivered') and not exists (
      select 1 from public.drone_inventory inventory join public.drone_credentials credential
      on credential.drone_id=inventory.inventory_id
      where inventory.inventory_id=command.drone_id and inventory.station_id=command.station_id
      and inventory.lake_id=command.lake_id and inventory.source='real' and inventory.lifecycle<>'retired'
      and credential.credential_id=command.credential_id and credential.station_id=command.station_id and credential.credential_state='active');
end; $$;

create function public.queue_real_patrol(p_station_id uuid,p_drone_id uuid,p_lake_id text,p_actor uuid,p_payload jsonb)
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

create function public.real_patrol_status(p_station_id uuid,p_drone_id uuid,p_command_id uuid)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare command public.real_patrol_commands%rowtype;
begin
  perform private.refresh_real_patrols(p_drone_id);
  select * into command from public.real_patrol_commands where command_id=p_command_id and drone_id=p_drone_id and station_id=p_station_id;
  if not found then return null; end if;
  return jsonb_build_object('command_id',command.command_id,'status',command.status,'detail',command.detail,'expires_at',command.expires_at);
end; $$;

create function public.latest_real_patrol(p_station_id uuid,p_drone_id uuid)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare command_id uuid;
begin
  select command.command_id into command_id from public.real_patrol_commands command
    where station_id=p_station_id and drone_id=p_drone_id order by created_at desc,command.command_id desc limit 1;
  if not found then return null; end if;
  return public.real_patrol_status(p_station_id,p_drone_id,command_id);
end; $$;

create function public.deliver_real_patrols(p_drone_id uuid,p_credential_id uuid)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare credential public.drone_credentials%rowtype; result jsonb;
begin
  select * into credential from public.drone_credentials where credential_id=p_credential_id and drone_id=p_drone_id and credential_state='active' for update;
  if not found then return '[]'::jsonb; end if;
  perform 1 from public.drone_inventory where inventory_id=p_drone_id for update;
  perform private.refresh_real_patrols(p_drone_id);
  with delivered as (
    update public.real_patrol_commands set status='delivered',delivered_at=coalesce(delivered_at,now())
    where drone_id=p_drone_id and credential_id=p_credential_id and status in ('queued','delivered') and expires_at>now()
    returning *
  ) select coalesce(jsonb_agg(payload || jsonb_build_object('command_id',command_id,'command_type','patrol',
      'expires_at',expires_at,'ack',true,'patrol_ack',true)),'[]'::jsonb) into result from delivered;
  return result;
end; $$;

create function public.reject_real_patrol(p_drone_id uuid,p_command_id uuid,p_detail text)
returns void language plpgsql security definer set search_path = '' as $$
begin
  update public.real_patrol_commands set status='rejected',detail=left(p_detail,500)
    where command_id=p_command_id and drone_id=p_drone_id and status in ('queued','delivered');
end; $$;

create function public.acknowledge_real_patrol(p_drone_id uuid,p_credential_id uuid,p_command_id uuid,p_sequence bigint,p_status text,p_detail text)
returns boolean language plpgsql security definer set search_path = '' as $$
declare credential public.drone_credentials%rowtype; command public.real_patrol_commands%rowtype;
begin
  if p_status is null or p_status not in ('accepted','rejected') or p_sequence is null then return false; end if;
  select * into credential from public.drone_credentials where credential_id=p_credential_id and drone_id=p_drone_id and credential_state='active' for update;
  if not found or p_sequence<=credential.last_sequence then return false; end if;
  perform 1 from public.drone_inventory where inventory_id=p_drone_id for update;
  perform private.refresh_real_patrols(p_drone_id);
  select * into command from public.real_patrol_commands where command_id=p_command_id and drone_id=p_drone_id
    and credential_id=p_credential_id for update;
  if not found or command.status not in ('delivered','uploaded','rejected') or command.expires_at<=now() then return false; end if;
  -- A fresh signed retry of the same outcome is safe; a contrary outcome cannot overwrite it.
  if command.status in ('uploaded','rejected') and (command.acknowledgement_sequence is null
    or command.status is distinct from case when p_status='accepted' then 'uploaded' else 'rejected' end) then return false; end if;
  update public.drone_credentials set last_sequence=p_sequence where credential_id=p_credential_id;
  if command.acknowledgement_sequence is null then
    update public.real_patrol_commands set status=case when p_status='accepted' then 'uploaded' else 'rejected' end,
      detail=left(p_detail,500),acknowledged_at=now(),acknowledgement_sequence=p_sequence where command_id=p_command_id;
    insert into public.audit_events(actor_device_id,station_id,lake_id,request_id,action,decision,reason,resulting_state,source_context)
      values(p_drone_id,command.station_id,command.lake_id,gen_random_uuid(),'patrol.upload_ack','allowed','signed device upload result',
      jsonb_build_object('command_id',p_command_id,'status',p_status),
      jsonb_build_object('credential_id',p_credential_id,'sequence',p_sequence));
  end if;
  return true;
end; $$;

revoke all on function private.refresh_real_patrols(uuid) from public,anon,authenticated;
revoke all on function public.queue_real_patrol(uuid,uuid,text,uuid,jsonb),public.real_patrol_status(uuid,uuid,uuid),public.latest_real_patrol(uuid,uuid),
  public.deliver_real_patrols(uuid,uuid),public.reject_real_patrol(uuid,uuid,text),
  public.acknowledge_real_patrol(uuid,uuid,uuid,bigint,text,text) from public,anon,authenticated;
grant execute on function public.queue_real_patrol(uuid,uuid,text,uuid,jsonb),public.real_patrol_status(uuid,uuid,uuid),public.latest_real_patrol(uuid,uuid),
  public.deliver_real_patrols(uuid,uuid),public.reject_real_patrol(uuid,uuid,text),
  public.acknowledge_real_patrol(uuid,uuid,uuid,bigint,text,text) to service_role;
