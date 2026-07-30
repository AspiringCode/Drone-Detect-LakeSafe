-- Durable desired state for autonomous fleet circulation.  This migration adds
-- no human steering surface: inventory changes are mediated by backend code.

create table public.station_fleet_policies (
  station_id uuid primary key references public.stations(station_id) on delete restrict,
  simulated_inventory_allowance integer not null default 5 check (simulated_inventory_allowance >= 0),
  safety_reserve integer not null default 1 check (safety_reserve >= 0),
  minimum_battery_percent integer not null default 30 check (minimum_battery_percent between 0 and 100),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.drone_inventory (
  inventory_id uuid primary key default gen_random_uuid(),
  station_id uuid not null references public.stations(station_id) on delete restrict,
  lake_id text references public.lakes(lake_id) on delete restrict,
  source text not null check (source in ('simulated', 'real')),
  lifecycle text not null check (lifecycle in ('available', 'circulating', 'charging', 'maintenance', 'retired')),
  battery_percent integer not null default 100 check (battery_percent between 0 and 100),
  health text not null default 'healthy' check (health in ('healthy', 'fault')),
  connectivity text not null default 'connected' check (connectivity in ('connected', 'disconnected')),
  maintenance_due boolean not null default false,
  desired_state_version integer not null default 0 check (desired_state_version >= 0),
  acknowledged_state_version integer not null default 0 check (acknowledged_state_version >= 0 and acknowledged_state_version <= desired_state_version),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check ((lifecycle = 'circulating') = (lake_id is not null))
);

create table public.drone_availability_requests (
  availability_request_id uuid primary key default gen_random_uuid(),
  inventory_id uuid not null references public.drone_inventory(inventory_id) on delete restrict,
  station_id uuid not null references public.stations(station_id) on delete restrict,
  lake_id text not null references public.lakes(lake_id) on delete restrict,
  eligible boolean not null,
  reason text not null check (length(trim(reason)) between 1 and 500),
  requested_by uuid not null references auth.users(id) on delete restrict,
  created_at timestamptz not null default now()
);

create table public.zone_assignments (
  zone_assignment_id uuid primary key default gen_random_uuid(),
  zone_plan_id uuid not null references public.zone_plans(zone_plan_id) on delete restrict,
  zone_plan_cell_id uuid not null references public.zone_plan_cells(zone_plan_cell_id) on delete restrict,
  inventory_id uuid not null references public.drone_inventory(inventory_id) on delete restrict,
  station_id uuid not null references public.stations(station_id) on delete restrict,
  lake_id text not null references public.lakes(lake_id) on delete restrict,
  desired_state_version integer not null check (desired_state_version > 0),
  created_at timestamptz not null default now(),
  unique (inventory_id, desired_state_version),
  unique (zone_plan_id, inventory_id),
  unique (zone_plan_id, zone_plan_cell_id)
);

create table public.command_outbox (
  command_id uuid primary key default gen_random_uuid(),
  inventory_id uuid not null references public.drone_inventory(inventory_id) on delete restrict,
  zone_assignment_id uuid not null references public.zone_assignments(zone_assignment_id) on delete restrict,
  station_id uuid not null references public.stations(station_id) on delete restrict,
  lake_id text not null references public.lakes(lake_id) on delete restrict,
  desired_state_version integer not null check (desired_state_version > 0),
  command_type text not null check (command_type in ('apply_assignment', 'return_to_reserve', 'safety_hold')),
  payload jsonb not null default '{}'::jsonb,
  status text not null default 'pending' check (status in ('pending', 'claimed', 'acknowledged', 'failed')),
  idempotency_key text not null unique,
  created_at timestamptz not null default now(),
  claimed_at timestamptz,
  acknowledged_at timestamptz,
  unique (inventory_id, desired_state_version),
  check ((status = 'claimed') = (claimed_at is not null)),
  check ((status = 'acknowledged') = (acknowledged_at is not null))
);

create or replace function private.assert_simulated_autonomy_ownership()
returns trigger language plpgsql set search_path = '' as $$
declare inventory_station uuid; lake_station uuid; plan_station uuid; plan_lake text; cell_plan uuid;
  inventory_lake text; inventory_source text; inventory_lifecycle text; inventory_health text;
  inventory_connectivity text; inventory_maintenance boolean; inventory_battery integer; minimum_battery integer;
  plan_status text; assignment_plan uuid; assignment_inventory uuid; assignment_version integer;
begin
  if tg_table_name = 'drone_inventory' and new.lake_id is not null then
    select station_id into lake_station from public.lakes where lake_id = new.lake_id;
    if lake_station is distinct from new.station_id then raise exception 'inventory lake must belong to station' using errcode = '23514'; end if;
  elsif tg_table_name = 'drone_availability_requests' then
    select station_id, lake_id, source, lifecycle, health, connectivity, maintenance_due, battery_percent
      into inventory_station, inventory_lake, inventory_source, inventory_lifecycle, inventory_health, inventory_connectivity, inventory_maintenance, inventory_battery
      from public.drone_inventory where inventory_id = new.inventory_id;
    select station_id into lake_station from public.lakes where lake_id = new.lake_id;
    select minimum_battery_percent into minimum_battery from public.station_fleet_policies where station_id = new.station_id;
    if inventory_station is distinct from new.station_id or lake_station is distinct from new.station_id
      or minimum_battery is null or inventory_lake is distinct from new.lake_id or inventory_source <> 'simulated'
      or inventory_lifecycle <> 'circulating' or inventory_health <> 'healthy'
      or inventory_connectivity <> 'connected' or inventory_maintenance or inventory_battery < minimum_battery
    then raise exception 'availability request requires eligible simulated circulating inventory' using errcode = '23514'; end if;
  elsif tg_table_name = 'zone_assignments' then
    select station_id, lake_id, status into plan_station, plan_lake, plan_status from public.zone_plans where zone_plan_id = new.zone_plan_id;
    select zone_plan_id into cell_plan from public.zone_plan_cells where zone_plan_cell_id = new.zone_plan_cell_id;
    select station_id, lake_id, source, lifecycle, health, connectivity, maintenance_due, battery_percent
      into inventory_station, inventory_lake, inventory_source, inventory_lifecycle, inventory_health, inventory_connectivity, inventory_maintenance, inventory_battery
      from public.drone_inventory where inventory_id = new.inventory_id;
    select minimum_battery_percent into minimum_battery from public.station_fleet_policies where station_id = new.station_id;
    if plan_station is distinct from new.station_id or plan_lake is distinct from new.lake_id or plan_status <> 'active'
      or cell_plan is distinct from new.zone_plan_id or inventory_station is distinct from new.station_id
      or minimum_battery is null or inventory_lake is distinct from new.lake_id or inventory_source <> 'simulated'
      or inventory_lifecycle <> 'circulating' or inventory_health <> 'healthy'
      or inventory_connectivity <> 'connected' or inventory_maintenance or inventory_battery < minimum_battery
    then raise exception 'assignment requires eligible simulated inventory and active plan cell' using errcode = '23514'; end if;
  elsif tg_table_name = 'command_outbox' then
    select station_id, lake_id, source, lifecycle, health, connectivity, maintenance_due, battery_percent
      into inventory_station, inventory_lake, inventory_source, inventory_lifecycle, inventory_health, inventory_connectivity, inventory_maintenance, inventory_battery
      from public.drone_inventory where inventory_id = new.inventory_id;
    select station_id into lake_station from public.lakes where lake_id = new.lake_id;
    select zone_plan_id, inventory_id, desired_state_version into assignment_plan, assignment_inventory, assignment_version from public.zone_assignments where zone_assignment_id = new.zone_assignment_id;
    select status into plan_status from public.zone_plans where zone_plan_id = assignment_plan;
    select minimum_battery_percent into minimum_battery from public.station_fleet_policies where station_id = new.station_id;
    if inventory_station is distinct from new.station_id or lake_station is distinct from new.station_id
      or minimum_battery is null or inventory_lake is distinct from new.lake_id or inventory_source <> 'simulated'
      or inventory_lifecycle <> 'circulating' or inventory_health <> 'healthy'
      or inventory_connectivity <> 'connected' or inventory_maintenance or inventory_battery < minimum_battery
      or assignment_inventory is distinct from new.inventory_id or assignment_version is distinct from new.desired_state_version or plan_status <> 'active'
    then raise exception 'command requires eligible simulated inventory and active assignment' using errcode = '23514'; end if;
  end if;
  return new;
end;
$$;

create function private.assert_simulated_allowance()
returns trigger language plpgsql set search_path = '' as $$
declare allowance integer; existing_count integer;
begin
  if new.source <> 'simulated' then return new; end if;
  select simulated_inventory_allowance into allowance from public.station_fleet_policies where station_id = new.station_id for update;
  if allowance is null then raise exception 'station fleet policy is required before simulated inventory' using errcode = '23514'; end if;
  select count(*) into existing_count from public.drone_inventory
    where station_id = new.station_id and source = 'simulated'
      and inventory_id is distinct from new.inventory_id;
  if existing_count >= allowance then raise exception 'simulated inventory allowance exceeded' using errcode = '23514'; end if;
  return new;
end;
$$;

create trigger drone_inventory_station_matches_lake before insert or update on public.drone_inventory for each row execute procedure private.assert_simulated_autonomy_ownership();
create trigger availability_request_station_matches_inputs before insert on public.drone_availability_requests for each row execute procedure private.assert_simulated_autonomy_ownership();
create trigger assignment_station_matches_inputs before insert on public.zone_assignments for each row execute procedure private.assert_simulated_autonomy_ownership();
create trigger outbox_station_matches_inputs before insert on public.command_outbox for each row execute procedure private.assert_simulated_autonomy_ownership();
create trigger drone_inventory_simulated_allowance before insert or update of source, station_id on public.drone_inventory for each row execute procedure private.assert_simulated_allowance();

create or replace function private.prevent_autonomy_history_mutation()
returns trigger language plpgsql set search_path = '' as $$
begin raise exception '% is immutable', tg_table_name using errcode = '55000'; end;
$$;
create trigger zone_assignments_immutable before update or delete on public.zone_assignments for each row execute procedure private.prevent_autonomy_history_mutation();
create trigger availability_requests_immutable before update or delete on public.drone_availability_requests for each row execute procedure private.prevent_autonomy_history_mutation();

alter table public.station_fleet_policies enable row level security;
alter table public.station_fleet_policies force row level security;
alter table public.drone_inventory enable row level security;
alter table public.drone_inventory force row level security;
alter table public.drone_availability_requests enable row level security;
alter table public.drone_availability_requests force row level security;
alter table public.zone_assignments enable row level security;
alter table public.zone_assignments force row level security;
alter table public.command_outbox enable row level security;
alter table public.command_outbox force row level security;

revoke all on public.station_fleet_policies, public.drone_inventory, public.drone_availability_requests, public.zone_assignments, public.command_outbox from public, anon, authenticated;
grant select on public.station_fleet_policies, public.drone_inventory, public.drone_availability_requests, public.zone_assignments, public.command_outbox to authenticated;
create policy station_fleet_policies_select_member on public.station_fleet_policies for select to authenticated using (private.is_active_station_member(auth.uid(), station_id));
create policy drone_inventory_select_member on public.drone_inventory for select to authenticated using (private.is_active_station_member(auth.uid(), station_id));
create policy drone_availability_requests_select_member on public.drone_availability_requests for select to authenticated using (private.is_active_station_member(auth.uid(), station_id));
create policy zone_assignments_select_member on public.zone_assignments for select to authenticated using (private.is_active_station_member(auth.uid(), station_id));
create policy command_outbox_select_member on public.command_outbox for select to authenticated using (private.is_active_station_member(auth.uid(), station_id));

revoke all on function private.assert_simulated_autonomy_ownership() from public, anon, authenticated;
revoke all on function private.assert_simulated_allowance() from public, anon, authenticated;
revoke all on function private.prevent_autonomy_history_mutation() from public, anon, authenticated;
