-- Signed heartbeat updates are server-only and never expose pilot controls.
create table public.real_capacity_reconciliations (
  reconciliation_id uuid primary key default gen_random_uuid(),
  lake_id text not null references public.lakes(lake_id) on delete restrict,
  trigger text not null check (trigger in ('heartbeat_recovery', 'heartbeat_expired')),
  created_at timestamptz not null default now()
);

create or replace function public.record_real_heartbeat(
  p_drone_id uuid, p_station_id uuid, p_credential_id uuid, p_battery_percent integer,
  p_health text, p_connected boolean, p_received_at timestamptz
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_inventory public.drone_inventory%rowtype; v_credential public.drone_credentials%rowtype;
  v_before_eligible boolean; v_after_eligible boolean; v_minimum integer;
begin
  if p_battery_percent not between 0 and 100 or p_health not in ('healthy', 'fault') then
    return null;
  end if;
  select * into v_credential from public.drone_credentials where credential_id=p_credential_id
    and drone_id=p_drone_id and station_id=p_station_id and credential_state='active' for update;
  select * into v_inventory from public.drone_inventory where inventory_id=p_drone_id
    and station_id=p_station_id and source='real' for update;
  if v_credential.credential_id is null or v_inventory.inventory_id is null then return null; end if;
  select minimum_battery_percent into v_minimum from public.station_fleet_policies where station_id=p_station_id;
  v_before_eligible := v_inventory.lake_id is not null and v_inventory.lifecycle='circulating'
    and v_inventory.health='healthy' and v_inventory.connectivity='connected'
    and not v_inventory.maintenance_due and v_inventory.battery_percent >= coalesce(v_minimum, 101);
  update public.drone_inventory set battery_percent=p_battery_percent, health=p_health,
    connectivity=case when p_connected then 'connected' else 'disconnected' end, updated_at=now()
    where inventory_id=p_drone_id returning * into v_inventory;
  insert into public.drone_heartbeats(drone_id, sequence, received_at, payload)
    values(p_drone_id, v_credential.last_sequence, p_received_at,
      jsonb_build_object('battery_percent',p_battery_percent,'health',p_health,'connected',p_connected));
  insert into public.drone_telemetry(drone_id, sequence, received_at, payload)
    values(p_drone_id, v_credential.last_sequence, p_received_at,
      jsonb_build_object('battery_percent',p_battery_percent,'health',p_health,'connected',p_connected));
  v_after_eligible := v_inventory.lake_id is not null and v_inventory.lifecycle='circulating'
    and v_inventory.health='healthy' and v_inventory.connectivity='connected'
    and not v_inventory.maintenance_due and v_inventory.battery_percent >= coalesce(v_minimum, 101);
  return jsonb_build_object('eligible',v_after_eligible,'lake_id',v_inventory.lake_id,
    'eligibility_changed',(not v_before_eligible and v_after_eligible));
end; $$;

create or replace function public.expire_stale_real_capacity(p_now timestamptz, p_ttl_seconds integer)
returns table(lake_id text) language plpgsql security definer set search_path = '' as $$
begin
  if p_ttl_seconds <> 15 then raise exception 'heartbeat ttl is fixed' using errcode='22023'; end if;
  return query with stale as (
    select i.inventory_id, i.lake_id from public.drone_inventory i
    join public.drone_credentials c on c.drone_id=i.inventory_id and c.station_id=i.station_id
    join lateral (select max(h.received_at) as received_at from public.drone_heartbeats h where h.drone_id=i.inventory_id) hb on true
    join public.station_fleet_policies p on p.station_id=i.station_id
    where i.source='real' and i.lifecycle='circulating' and i.lake_id is not null
      and i.health='healthy' and i.connectivity='connected' and not i.maintenance_due
      and i.battery_percent >= p.minimum_battery_percent and c.credential_state='active'
      and (hb.received_at is null or hb.received_at < p_now - make_interval(secs => p_ttl_seconds))
    for update of i skip locked
  ), changed as (
    update public.drone_inventory i set connectivity='disconnected', updated_at=p_now
    from stale where i.inventory_id=stale.inventory_id returning stale.lake_id
  ) select distinct changed.lake_id from changed;
end; $$;

create or replace function public.request_real_capacity_reconciliation(p_lake_id text, p_trigger text)
returns void language plpgsql security definer set search_path = '' as $$
begin
  if p_trigger not in ('heartbeat_recovery', 'heartbeat_expired') or not exists(select 1 from public.lakes where lake_id=p_lake_id) then
    raise exception 'invalid real capacity reconciliation' using errcode='23514';
  end if;
  insert into public.real_capacity_reconciliations(lake_id, trigger) values(p_lake_id,p_trigger);
end; $$;

alter table public.real_capacity_reconciliations enable row level security;
alter table public.real_capacity_reconciliations force row level security;
revoke all on public.real_capacity_reconciliations from public, anon, authenticated;
revoke all on function public.record_real_heartbeat(uuid,uuid,uuid,integer,text,boolean,timestamptz), public.expire_stale_real_capacity(timestamptz,integer), public.request_real_capacity_reconciliation(text,text) from public, anon, authenticated;
grant execute on function public.record_real_heartbeat(uuid,uuid,uuid,integer,text,boolean,timestamptz), public.expire_stale_real_capacity(timestamptz,integer), public.request_real_capacity_reconciliation(text,text) to service_role;
