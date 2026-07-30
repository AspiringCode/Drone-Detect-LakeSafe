-- Bind the authenticated sequence, durable telemetry, capacity update, and
-- reconciliation request in one transaction.  A queue row represents a lake,
-- not an individual device, so simultaneous capacity changes coalesce.
alter table public.real_capacity_reconciliations
  add column status text not null default 'pending' check (status in ('pending','claimed','complete')),
  add column generation bigint not null default 1,
  add column claim_token uuid,
  add column claim_expires_at timestamptz,
  add column attempts integer not null default 0 check (attempts >= 0),
  add column next_attempt_at timestamptz not null default now();
create unique index real_capacity_one_active_lake
  on public.real_capacity_reconciliations(lake_id) where status in ('pending','claimed');

create or replace function private.enqueue_real_capacity_reconciliation(p_lake_id text, p_trigger text)
returns void language plpgsql set search_path='' as $$
begin
  insert into public.real_capacity_reconciliations(lake_id, trigger, status, generation, next_attempt_at)
    values(p_lake_id,p_trigger,'pending',1,now())
  on conflict (lake_id) where status in ('pending','claimed') do update
    set trigger=excluded.trigger, generation=public.real_capacity_reconciliations.generation+1,
        status='pending', claim_token=null, claim_expires_at=null, next_attempt_at=now();
end; $$;

drop function public.record_real_heartbeat(uuid,uuid,uuid,integer,text,boolean,timestamptz);
create function public.record_real_heartbeat(
  p_drone_id uuid, p_station_id uuid, p_credential_id uuid, p_sequence bigint,
  p_battery_percent integer, p_health text, p_connected boolean, p_received_at timestamptz
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_inventory public.drone_inventory%rowtype; v_credential public.drone_credentials%rowtype;
  v_before_eligible boolean; v_after_eligible boolean; v_minimum integer;
begin
  if p_sequence < 0 or p_battery_percent not between 0 and 100 or p_health not in ('healthy', 'fault') then return null; end if;
  select * into v_credential from public.drone_credentials where credential_id=p_credential_id and drone_id=p_drone_id and station_id=p_station_id and credential_state='active' for update;
  select * into v_inventory from public.drone_inventory where inventory_id=p_drone_id and station_id=p_station_id and source='real' for update;
  if v_credential.credential_id is null or v_inventory.inventory_id is null or v_credential.last_sequence >= p_sequence then return null; end if;
  select minimum_battery_percent into v_minimum from public.station_fleet_policies where station_id=p_station_id;
  v_before_eligible := v_inventory.lake_id is not null and v_inventory.lifecycle='circulating' and v_inventory.health='healthy' and v_inventory.connectivity='connected' and not v_inventory.maintenance_due and v_inventory.battery_percent >= coalesce(v_minimum,101);
  update public.drone_credentials set last_sequence=p_sequence where credential_id=p_credential_id;
  update public.drone_inventory set battery_percent=p_battery_percent, health=p_health, connectivity=case when p_connected then 'connected' else 'disconnected' end, updated_at=now() where inventory_id=p_drone_id returning * into v_inventory;
  insert into public.drone_heartbeats(drone_id,sequence,received_at,payload) values(p_drone_id,p_sequence,p_received_at,jsonb_build_object('battery_percent',p_battery_percent,'health',p_health,'connected',p_connected));
  insert into public.drone_telemetry(drone_id,sequence,received_at,payload) values(p_drone_id,p_sequence,p_received_at,jsonb_build_object('battery_percent',p_battery_percent,'health',p_health,'connected',p_connected));
  v_after_eligible := v_inventory.lake_id is not null and v_inventory.lifecycle='circulating' and v_inventory.health='healthy' and v_inventory.connectivity='connected' and not v_inventory.maintenance_due and v_inventory.battery_percent >= coalesce(v_minimum,101);
  if not v_before_eligible and v_after_eligible then perform private.enqueue_real_capacity_reconciliation(v_inventory.lake_id,'heartbeat_recovery'); end if;
  return jsonb_build_object('eligible',v_after_eligible,'lake_id',v_inventory.lake_id,'eligibility_changed',(not v_before_eligible and v_after_eligible));
end; $$;

create or replace function public.expire_stale_real_capacity(p_now timestamptz, p_ttl_seconds integer)
returns table(lake_id text) language plpgsql security definer set search_path = '' as $$
declare v_lake_id text;
begin
  if p_ttl_seconds <> 15 then raise exception 'heartbeat ttl is fixed' using errcode='22023'; end if;
  for v_lake_id in with stale as (
    select i.inventory_id,i.lake_id from public.drone_inventory i join public.drone_credentials c on c.drone_id=i.inventory_id and c.station_id=i.station_id
    join lateral (select max(h.received_at) received_at from public.drone_heartbeats h where h.drone_id=i.inventory_id) hb on true
    join public.station_fleet_policies p on p.station_id=i.station_id
    where i.source='real' and i.lifecycle='circulating' and i.lake_id is not null and i.health='healthy' and i.connectivity='connected' and not i.maintenance_due and i.battery_percent>=p.minimum_battery_percent and c.credential_state='active' and (hb.received_at is null or hb.received_at < p_now-make_interval(secs=>p_ttl_seconds)) for update of i skip locked
  ), changed as (update public.drone_inventory i set connectivity='disconnected',updated_at=p_now from stale where i.inventory_id=stale.inventory_id returning stale.lake_id)
  select distinct changed.lake_id from changed loop
    perform private.enqueue_real_capacity_reconciliation(v_lake_id,'heartbeat_expired');
    lake_id := v_lake_id; return next;
  end loop;
end; $$;

create or replace function public.claim_real_capacity_reconciliations(p_limit integer, p_lease_seconds integer)
returns table(reconciliation_id uuid,lake_id text,trigger text,generation bigint,claim_token uuid) language plpgsql security definer set search_path='' as $$
begin
  if p_limit not between 1 and 100 or p_lease_seconds not between 1 and 300 then raise exception 'invalid queue claim' using errcode='22023'; end if;
  return query with candidates as (select r.reconciliation_id from public.real_capacity_reconciliations r where (r.status='pending' and r.next_attempt_at<=now()) or (r.status='claimed' and r.claim_expires_at<=now()) order by r.created_at for update skip locked limit p_limit), claimed as (update public.real_capacity_reconciliations r set status='claimed',claim_token=gen_random_uuid(),claim_expires_at=now()+make_interval(secs=>p_lease_seconds),attempts=r.attempts+1 from candidates c where r.reconciliation_id=c.reconciliation_id returning r.reconciliation_id,r.lake_id,r.trigger,r.generation,r.claim_token) select * from claimed;
end; $$;
create or replace function public.complete_real_capacity_reconciliation(p_reconciliation_id uuid,p_claim_token uuid,p_generation bigint)
returns boolean language plpgsql security definer set search_path='' as $$
begin update public.real_capacity_reconciliations set status='complete',claim_token=null,claim_expires_at=null where reconciliation_id=p_reconciliation_id and status='claimed' and claim_token=p_claim_token and generation=p_generation; return found; end; $$;
create or replace function public.release_real_capacity_reconciliation(p_reconciliation_id uuid,p_claim_token uuid)
returns boolean language plpgsql security definer set search_path='' as $$
begin update public.real_capacity_reconciliations set status='pending',claim_token=null,claim_expires_at=null,next_attempt_at=now()+make_interval(secs=>least(60,attempts*2)) where reconciliation_id=p_reconciliation_id and status='claimed' and claim_token=p_claim_token; return found; end; $$;

drop function public.request_real_capacity_reconciliation(text,text);
create function public.request_real_capacity_reconciliation(p_lake_id text,p_trigger text) returns void language plpgsql security definer set search_path='' as $$ begin if p_trigger not in ('heartbeat_recovery','heartbeat_expired') or not exists(select 1 from public.lakes where lake_id=p_lake_id) then raise exception 'invalid real capacity reconciliation' using errcode='23514'; end if; perform private.enqueue_real_capacity_reconciliation(p_lake_id,p_trigger); end; $$;
create function public.reconcile_real_capacity(p_lake_id text,p_trigger text) returns void language plpgsql security definer set search_path='' as $$ begin
  -- The durable worker calls this hook after claiming a queue lease.  It
  -- publishes an internal wake-up for the autonomy service; no route, heading,
  -- waypoint, or manual control is ever accepted here.
  perform pg_notify('lakesafe_real_capacity', json_build_object('lake_id',p_lake_id,'trigger',p_trigger)::text);
end; $$;
revoke all on function public.record_real_heartbeat(uuid,uuid,uuid,bigint,integer,text,boolean,timestamptz), public.claim_real_capacity_reconciliations(integer,integer), public.complete_real_capacity_reconciliation(uuid,uuid,bigint), public.release_real_capacity_reconciliation(uuid,uuid), public.request_real_capacity_reconciliation(text,text) from public,anon,authenticated;
grant execute on function public.record_real_heartbeat(uuid,uuid,uuid,bigint,integer,text,boolean,timestamptz), public.claim_real_capacity_reconciliations(integer,integer), public.complete_real_capacity_reconciliation(uuid,uuid,bigint), public.release_real_capacity_reconciliation(uuid,uuid), public.request_real_capacity_reconciliation(text,text) to service_role;
revoke all on function public.reconcile_real_capacity(text,text) from public,anon,authenticated;
grant execute on function public.reconcile_real_capacity(text,text) to service_role;
