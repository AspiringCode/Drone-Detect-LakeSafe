-- Separate independent observations, operator decisions, and acknowledged flight intent.
alter table public.operational_alerts add column review_decision text
  check (review_decision in ('confirmed','dismissed','ended'));
create table public.alert_investigations (
  alert_id text primary key references public.operational_alerts(alert_id),
  station_id uuid not null references public.stations(station_id),
  lake_id text not null references public.lakes(lake_id),
  detecting text not null,
  confirmer uuid references public.drone_inventory(inventory_id),
  phase text not null check (phase in ('en_route','awaiting_finding','finding_received','returning','returned','unavailable','failed')),
  finding text check (finding in ('observed','not_observed','inconclusive')),
  finding_alert_id text references public.operational_alerts(alert_id),
  detail text,
  deadline timestamptz not null default now()+interval '5 minutes',
  created_at timestamptz not null default now()
);
create unique index one_live_investigation_per_lake on public.alert_investigations(lake_id)
  where phase in ('en_route','awaiting_finding','finding_received','returning');
create table public.investigation_commands (
  command_id uuid primary key default gen_random_uuid(),
  alert_id text not null references public.alert_investigations(alert_id),
  drone_id uuid not null references public.drone_inventory(inventory_id),
  credential_id uuid not null references public.drone_credentials(credential_id),
  desired_version integer not null,
  kind text not null check (kind in ('investigate','resume_patrol')),
  payload jsonb not null,
  status text not null default 'queued' check (status in ('queued','accepted','rejected','superseded')),
  detail text,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null default now()+interval '120 seconds',
  unique(alert_id,kind)
);
alter table public.alert_investigations enable row level security;
alter table public.alert_investigations force row level security;
alter table public.investigation_commands enable row level security;
alter table public.investigation_commands force row level security;
revoke all on public.alert_investigations,public.investigation_commands from public,anon,authenticated;
grant select on public.alert_investigations,public.investigation_commands to service_role;

create function private.end_investigation(p_alert_id text) returns void
language plpgsql set search_path='' as $$
declare incident public.alert_investigations%rowtype; prior public.investigation_commands%rowtype;
begin
  select * into incident from public.alert_investigations where alert_id=p_alert_id for update;
  if not found or incident.phase in ('returning','returned') or incident.confirmer is null then return; end if;
  select * into prior from public.investigation_commands where alert_id=p_alert_id and kind='investigate';
  update public.investigation_commands set status='superseded' where alert_id=p_alert_id and status='queued';
  insert into public.investigation_commands(alert_id,drone_id,credential_id,desired_version,kind,payload)
    values(p_alert_id,prior.drone_id,prior.credential_id,prior.desired_version,'resume_patrol',jsonb_build_object('investigation_id',p_alert_id))
    on conflict(alert_id,kind) do nothing;
  update public.alert_investigations set phase='returning',detail='Return requested; awaiting aircraft acknowledgement' where alert_id=p_alert_id;
end; $$;

create function public.begin_real_investigation(p_lake_id text,p_alert_id text,p_second uuid,p_origin jsonb) returns jsonb
language plpgsql security definer set search_path='' as $$
declare a public.operational_alerts%rowtype; incident public.alert_investigations%rowtype;
  device public.drone_inventory%rowtype; credential public.drone_credentials%rowtype; path public.geometry; target public.geometry;
begin
  perform pg_advisory_xact_lock(hashtextextended(p_lake_id,0));
  select * into a from public.operational_alerts where alert_id=p_alert_id and lake_id=p_lake_id and source='real';
  if not found then return null; end if;
  -- Only an independently signed, nearby, recent report from the assigned second aircraft corroborates.
  select * into incident from public.alert_investigations where lake_id=p_lake_id
    and confirmer::text=a.hardware_ref and phase in ('en_route','awaiting_finding','finding_received')
    and deadline>now() and a.occurred_at>=created_at-interval '10 seconds' for update;
  if found and exists(select 1 from public.operational_alerts first_alert where first_alert.alert_id=incident.alert_id
    and public.st_dwithin(first_alert.precise_location::public.geography,a.precise_location::public.geography,60)) then
    update public.alert_investigations set phase='finding_received',finding='observed',finding_alert_id=a.alert_id,
      detail='Independent signed thermal detection received' where alert_id=incident.alert_id;
    return jsonb_build_object('corroborates',incident.alert_id);
  end if;
  if exists(select 1 from public.alert_investigations where alert_id=p_alert_id) then return null; end if;
  if exists(select 1 from public.alert_investigations where lake_id=p_lake_id
    and phase in ('en_route','awaiting_finding','finding_received','returning')) then
    insert into public.alert_investigations(alert_id,station_id,lake_id,detecting,phase,detail)
      values(a.alert_id,a.station_id,a.lake_id,a.hardware_ref,'unavailable','Another investigation is active');
    return null;
  end if;
  select * into credential from public.drone_credentials where drone_id=p_second and credential_state='active' for update;
  select * into device from public.drone_inventory where inventory_id=p_second for update;
  if p_origin is not null then
    path:=public.st_makeline(public.st_setsrid(public.st_makepoint((p_origin->>'lon')::float8,(p_origin->>'lat')::float8),4326),a.precise_location);
  end if;
  if p_second::text is not distinct from a.hardware_ref or device.station_id is distinct from a.station_id
    or device.lake_id is distinct from a.lake_id or device.source is distinct from 'real'
    or device.lifecycle is distinct from 'circulating' or device.health is distinct from 'healthy'
    or device.connectivity is distinct from 'connected' or device.maintenance_due
    or credential.credential_id is null or device.battery_percent < coalesce((select minimum_battery_percent from public.station_fleet_policies where station_id=a.station_id),101)
    or not exists(select 1 from public.drone_heartbeats where drone_id=p_second and received_at>now()-interval '10 seconds')
    or not exists(select 1 from public.real_fleet_safety_policies where lake_id=a.lake_id and station_id=a.station_id and autonomy_state='active' and not safe_return_required)
    or path is null or not exists(select 1 from public.lakes where lake_id=a.lake_id and public.st_covers(shoreline,path))
    or exists(select 1 from public.real_patrol_commands where drone_id=p_second and status in ('queued','delivered') and expires_at>now()) then
    insert into public.alert_investigations(alert_id,station_id,lake_id,detecting,phase,detail)
      values(a.alert_id,a.station_id,a.lake_id,a.hardware_ref,'unavailable','No eligible second aircraft, or real autonomy is not active');
    return null;
  end if;
  insert into public.alert_investigations(alert_id,station_id,lake_id,detecting,confirmer,phase)
    values(a.alert_id,a.station_id,a.lake_id,a.hardware_ref,p_second,'en_route');
  -- Stop twenty metres short of the detecting drone, on the validated water-only segment.
  target:=public.st_lineinterpolatepoint(path,greatest(0,1-20/greatest(public.st_length(path::public.geography),1)));
  insert into public.investigation_commands(alert_id,drone_id,credential_id,desired_version,kind,payload)
    values(a.alert_id,p_second,credential.credential_id,device.desired_state_version,'investigate',
      jsonb_build_object('investigation_id',a.alert_id,'target',jsonb_build_object('lat',public.st_y(target),'lon',public.st_x(target))));
  return jsonb_build_object('alert_id',a.alert_id,'phase','en_route','confirmer',p_second);
end; $$;

create function public.decide_operational_alert(p_lake_id text,p_alert_id text,p_actor uuid,p_decision text) returns jsonb
language plpgsql security definer set search_path='' as $$
declare result jsonb; previous text;
begin
  if p_decision is null or p_decision not in ('confirmed','dismissed','ended') then return null; end if;
  result:=public.review_operational_alert(p_lake_id,p_alert_id,p_actor);
  if result is null then return null; end if;
  select review_decision into previous from public.operational_alerts where alert_id=p_alert_id for update;
  -- Retries are idempotent; a completed decision cannot be silently overwritten.
  if previous is not null and previous<>p_decision and not(previous='confirmed' and p_decision='ended') then
    raise exception 'alert already decided';
  end if;
  update public.operational_alerts set review_decision=p_decision where alert_id=p_alert_id;
  if p_decision in ('dismissed','ended') then perform private.end_investigation(p_alert_id); end if;
  perform private.record_workflow_audit(p_actor,(select station_id from public.operational_alerts where alert_id=p_alert_id),p_lake_id,
    'alert.decision','allowed',p_decision,null,jsonb_build_object('alert_id',p_alert_id));
  return result||jsonb_build_object('review_decision',p_decision);
end; $$;

create function public.real_investigation_states(p_lake_id text) returns jsonb
language sql security definer set search_path='' as $$
  select coalesce(jsonb_object_agg(a.alert_id,jsonb_build_object('review_decision',a.review_decision,
    'investigation',case when i.alert_id is null then null else jsonb_build_object('alert_id',i.alert_id,
      'detecting',i.detecting,'confirmer',i.confirmer,'phase',i.phase,'finding',i.finding,'detail',i.detail,'finding_alert_id',i.finding_alert_id) end)), '{}')
  from public.operational_alerts a left join public.alert_investigations i on i.alert_id=a.alert_id
  where a.lake_id=p_lake_id and a.source='real';
$$;

create function public.deliver_investigation_commands(p_drone_id uuid,p_credential_id uuid) returns jsonb
language plpgsql security definer set search_path='' as $$
declare incident record; result jsonb;
begin
  perform 1 from public.drone_credentials where credential_id=p_credential_id and drone_id=p_drone_id and credential_state='active' for update;
  if not found then return '[]'; end if;
  for incident in select alert_id from public.alert_investigations where confirmer=p_drone_id and deadline<=now()
    and phase in ('en_route','awaiting_finding','finding_received') for update loop
    update public.alert_investigations set finding=coalesce(finding,'inconclusive') where alert_id=incident.alert_id;
    perform private.end_investigation(incident.alert_id);
  end loop;
  update public.investigation_commands c set status='rejected',detail='Expired, reassigned, replanned, or fleet safety policy blocks investigation'
    where c.drone_id=p_drone_id and c.status='queued' and (c.expires_at<=now() or not exists (
      select 1 from public.drone_inventory d join public.alert_investigations i on i.alert_id=c.alert_id
      join public.real_fleet_safety_policies s on s.lake_id=i.lake_id and s.station_id=i.station_id
      where d.inventory_id=p_drone_id and d.station_id=i.station_id and d.lake_id=i.lake_id
      and d.source='real' and d.lifecycle='circulating' and d.desired_state_version=c.desired_version
      and d.health='healthy' and d.connectivity='connected' and not d.maintenance_due
      and d.battery_percent>=coalesce((select minimum_battery_percent from public.station_fleet_policies where station_id=d.station_id),101)
      and s.autonomy_state='active' and not s.safe_return_required and c.credential_id=p_credential_id));
  update public.alert_investigations i set phase='failed',detail=c.detail from public.investigation_commands c
    where c.alert_id=i.alert_id and c.drone_id=p_drone_id and c.status='rejected' and i.phase not in ('returned','failed');
  select coalesce(jsonb_agg(c.payload||jsonb_build_object('command_id',c.command_id,'command_type',c.kind,
    'expires_at',c.expires_at,'ack',true,'investigation_ack',true)),'[]') into result
    from public.investigation_commands c where c.drone_id=p_drone_id and c.credential_id=p_credential_id and c.status='queued';
  return result;
end; $$;

create function public.acknowledge_investigation_command(p_drone_id uuid,p_credential_id uuid,p_command_id uuid,p_sequence bigint,p_status text,p_detail text) returns boolean
language plpgsql security definer set search_path='' as $$
declare command public.investigation_commands%rowtype;
begin
  if p_status is null or p_status not in ('accepted','rejected') then return false; end if;
  perform 1 from public.drone_credentials where drone_id=p_drone_id and credential_id=p_credential_id and credential_state='active'
    and p_sequence>last_sequence for update;
  if not found then return false; end if;
  select * into command from public.investigation_commands where command_id=p_command_id and drone_id=p_drone_id
    and credential_id=p_credential_id for update;
  if not found or command.status='superseded' or command.expires_at<=now()
    or command.status not in ('queued',p_status) then return false; end if;
  update public.drone_credentials set last_sequence=p_sequence where credential_id=p_credential_id;
  update public.investigation_commands set status=p_status,detail=left(p_detail,500) where command_id=p_command_id;
  update public.alert_investigations set phase=case when p_status='rejected' then 'failed'
    when command.kind='resume_patrol' then 'returning' else 'awaiting_finding' end,
    detail=left(p_detail,500) where alert_id=command.alert_id and phase not in ('finding_received','returned');
  return true;
end; $$;

create function private.block_patrol_during_investigation() returns trigger
language plpgsql set search_path='' as $$
begin
  if exists(select 1 from public.alert_investigations where confirmer=new.drone_id and phase in ('en_route','awaiting_finding','finding_received','returning')) then
    raise exception 'End the active investigation before replacing the patrol mission';
  end if;
  return new;
end; $$;
create trigger protect_investigation_patrol before insert on public.real_patrol_commands
  for each row execute function private.block_patrol_during_investigation();

create function public.complete_real_investigation(p_drone_id uuid,p_credential_id uuid,p_sequence bigint,p_alert_id text) returns boolean
language plpgsql security definer set search_path='' as $$
begin
  if not exists(select 1 from public.drone_credentials where drone_id=p_drone_id and credential_id=p_credential_id
    and credential_state='active' and last_sequence=p_sequence) then return false; end if;
  update public.alert_investigations i set phase='returned',detail='Aircraft reported original patrol resumed'
    where i.alert_id=p_alert_id and i.confirmer=p_drone_id and (i.phase='returning'
      and exists(select 1 from public.investigation_commands c where c.alert_id=i.alert_id and c.kind='resume_patrol' and c.status='accepted')
      or i.deadline<=now() and i.phase in ('en_route','awaiting_finding','finding_received'));
  return found;
end; $$;

revoke all on function private.end_investigation(text),public.begin_real_investigation(text,text,uuid,jsonb),
  private.block_patrol_during_investigation(),
  public.decide_operational_alert(text,text,uuid,text),public.real_investigation_states(text),
  public.deliver_investigation_commands(uuid,uuid),public.acknowledge_investigation_command(uuid,uuid,uuid,bigint,text,text),public.complete_real_investigation(uuid,uuid,bigint,text) from public,anon,authenticated;
grant execute on function public.begin_real_investigation(text,text,uuid,jsonb),public.decide_operational_alert(text,text,uuid,text),
  public.real_investigation_states(text),public.deliver_investigation_commands(uuid,uuid),
  public.acknowledge_investigation_command(uuid,uuid,uuid,bigint,text,text),public.complete_real_investigation(uuid,uuid,bigint,text) to service_role;
