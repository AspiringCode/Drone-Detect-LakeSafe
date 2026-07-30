-- Real device identities are distinct from simulated inventory.  Only public
-- Ed25519 material is stored here; private signing keys stay in device storage.
create table public.drone_credentials (
  credential_id uuid primary key default gen_random_uuid(),
  drone_id uuid not null unique references public.drone_inventory(inventory_id) on delete restrict,
  station_id uuid not null references public.stations(station_id) on delete restrict,
  manufacturer text not null check (length(btrim(manufacturer)) > 0),
  serial text not null check (length(btrim(serial)) > 0),
  public_key text not null,
  key_fingerprint text not null unique,
  credential_state text not null default 'active' check (credential_state in ('active', 'revoked')),
  last_sequence bigint not null default -1 check (last_sequence >= -1),
  secret_key_ref text,
  created_at timestamptz not null default now(),
  revoked_at timestamptz,
  unique (manufacturer, serial),
  check ((credential_state = 'active' and revoked_at is null) or (credential_state = 'revoked' and revoked_at is not null))
);

create table public.drone_heartbeats (
  heartbeat_id uuid primary key default gen_random_uuid(), drone_id uuid not null references public.drone_inventory(inventory_id) on delete restrict,
  sequence bigint not null, received_at timestamptz not null default now(), payload jsonb not null, unique (drone_id, sequence)
);
create table public.drone_telemetry (
  telemetry_id uuid primary key default gen_random_uuid(), drone_id uuid not null references public.drone_inventory(inventory_id) on delete restrict,
  sequence bigint not null, received_at timestamptz not null default now(), payload jsonb not null, unique (drone_id, sequence)
);
create table public.command_acknowledgements (
  acknowledgement_id uuid primary key default gen_random_uuid(), drone_id uuid not null references public.drone_inventory(inventory_id) on delete restrict,
  command_id uuid not null references public.command_outbox(command_id) on delete restrict,
  sequence bigint not null, status text not null check (status in ('accepted', 'rejected', 'completed')),
  detail text, received_at timestamptz not null default now(), unique (drone_id, sequence), unique (command_id)
);

create or replace function public.claim_drone_sequence(p_drone_id uuid, p_sequence bigint)
returns boolean language plpgsql security definer set search_path = '' as $$
begin
  update public.drone_credentials set last_sequence = p_sequence
    where drone_id = p_drone_id and credential_state = 'active' and last_sequence < p_sequence;
  return found;
end; $$;

create or replace function public.register_real_drone(p_station_id uuid, p_manufacturer text, p_serial text, p_public_key text, p_actor_user_id uuid)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare v_drone_id uuid; v_credential_id uuid; v_fingerprint text;
begin
  if not exists (select 1 from public.stations where station_id=p_station_id and status='active') then return null; end if;
  v_fingerprint := encode(extensions.digest(convert_to(p_public_key, 'utf8'), 'sha256'), 'hex');
  insert into public.drone_inventory(station_id, source, lifecycle) values(p_station_id, 'real', 'available') returning inventory_id into v_drone_id;
  insert into public.drone_credentials(drone_id, station_id, manufacturer, serial, public_key, key_fingerprint)
    values(v_drone_id, p_station_id, btrim(p_manufacturer), btrim(p_serial), p_public_key, v_fingerprint) returning credential_id into v_credential_id;
  perform private.record_workflow_audit(p_actor_user_id, p_station_id, null, 'real_device.register', 'allowed', 'real device credential registered', null, jsonb_build_object('drone_id',v_drone_id,'credential_id',v_credential_id));
  return jsonb_build_object('drone_id',v_drone_id,'credential_id',v_credential_id,'station_id',p_station_id,'source','real','lifecycle','available');
exception when unique_violation then return null;
end; $$;

create or replace function public.retire_real_drone(p_station_id uuid, p_drone_id uuid, p_actor_user_id uuid)
returns jsonb language plpgsql security definer set search_path = '' as $$
begin
  update public.drone_credentials set credential_state='revoked', revoked_at=now() where drone_id=p_drone_id and station_id=p_station_id and credential_state='active';
  if not found then return null; end if;
  update public.drone_inventory set lifecycle='retired', lake_id=null, updated_at=now() where inventory_id=p_drone_id and station_id=p_station_id and source='real';
  perform private.record_workflow_audit(p_actor_user_id, p_station_id, null, 'real_device.retire', 'allowed', 'real device credential revoked', null, jsonb_build_object('drone_id',p_drone_id));
  return jsonb_build_object('drone_id',p_drone_id,'station_id',p_station_id,'source','real','lifecycle','retired');
end; $$;

create or replace function private.prevent_real_device_history_mutation() returns trigger language plpgsql set search_path='' as $$ begin raise exception '% is immutable',tg_table_name using errcode='55000'; end; $$;
create trigger heartbeats_append_only before update or delete on public.drone_heartbeats for each row execute procedure private.prevent_real_device_history_mutation();
create trigger telemetry_append_only before update or delete on public.drone_telemetry for each row execute procedure private.prevent_real_device_history_mutation();
create trigger acknowledgements_append_only before update or delete on public.command_acknowledgements for each row execute procedure private.prevent_real_device_history_mutation();

alter table public.drone_credentials enable row level security; alter table public.drone_credentials force row level security;
alter table public.drone_heartbeats enable row level security; alter table public.drone_heartbeats force row level security;
alter table public.drone_telemetry enable row level security; alter table public.drone_telemetry force row level security;
alter table public.command_acknowledgements enable row level security; alter table public.command_acknowledgements force row level security;
revoke all on public.drone_credentials, public.drone_heartbeats, public.drone_telemetry, public.command_acknowledgements from public, anon, authenticated;
revoke all on function public.claim_drone_sequence(uuid,bigint), public.register_real_drone(uuid,text,text,text,uuid), public.retire_real_drone(uuid,uuid,uuid) from public, anon, authenticated;
grant execute on function public.claim_drone_sequence(uuid,bigint), public.register_real_drone(uuid,text,text,text,uuid), public.retire_real_drone(uuid,uuid,uuid) to service_role;
revoke all on function private.prevent_real_device_history_mutation() from public, anon, authenticated;
