-- Reviewed connector records and the resulting data/zone artifacts are kept
-- versioned so a lake's active plan can always be traced to its exact inputs.

create table public.socrata_connectors (
  connector_id uuid primary key default gen_random_uuid(),
  connector_key text not null unique,
  domain text not null,
  dataset_id text not null,
  schema_version text not null,
  attribution text not null,
  configuration jsonb not null default '{}'::jsonb,
  review_status text not null check (review_status in ('reviewed', 'disabled', 'retired')),
  reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  check ((review_status = 'reviewed') = (reviewed_at is not null))
);

create table public.lake_data_sources (
  lake_data_source_id uuid primary key default gen_random_uuid(),
  lake_id text not null references public.lakes(lake_id) on delete restrict,
  station_id uuid not null references public.stations(station_id) on delete restrict,
  connector_id uuid not null references public.socrata_connectors(connector_id) on delete restrict,
  source_configuration jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (lake_id, connector_id)
);

create table public.risk_snapshots (
  snapshot_id uuid primary key default gen_random_uuid(),
  lake_id text not null references public.lakes(lake_id) on delete restrict,
  station_id uuid not null references public.stations(station_id) on delete restrict,
  status text not null check (status in ('ready', 'quarantined', 'failed')),
  source_fresh_through timestamptz,
  source_metadata jsonb not null,
  canonical_payload jsonb not null,
  payload_sha256 text not null check (payload_sha256 ~ '^[0-9a-f]{64}$'),
  failure_reason text,
  created_at timestamptz not null default now(),
  unique (lake_id, payload_sha256),
  check ((status = 'ready') = (failure_reason is null))
);

create table public.zone_plans (
  zone_plan_id uuid primary key default gen_random_uuid(),
  lake_id text not null references public.lakes(lake_id) on delete restrict,
  station_id uuid not null references public.stations(station_id) on delete restrict,
  snapshot_id uuid not null references public.risk_snapshots(snapshot_id) on delete restrict,
  version integer not null,
  status text not null check (status in ('candidate', 'validated', 'active', 'superseded', 'invalid')),
  algorithm_version text not null,
  prior_plan_id uuid references public.zone_plans(zone_plan_id) on delete restrict,
  validation_payload jsonb,
  created_at timestamptz not null default now(),
  activated_at timestamptz,
  unique (lake_id, version),
  check ((status = 'active') = (activated_at is not null))
);
create unique index zone_plans_one_active_per_lake
  on public.zone_plans (lake_id) where status = 'active';

create table public.zone_plan_cells (
  zone_plan_cell_id uuid primary key default gen_random_uuid(),
  zone_plan_id uuid not null references public.zone_plans(zone_plan_id) on delete restrict,
  ordinal integer not null check (ordinal >= 0),
  kind text not null check (kind in ('hotspot', 'coverage', 'fallback')),
  risk_score double precision not null check (risk_score >= 0),
  seed geometry(Point, 4326) not null,
  boundary geometry(Polygon, 4326) not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (zone_plan_id, ordinal),
  check (st_srid(seed) = 4326 and st_srid(boundary) = 4326)
);

create or replace function private.assert_risk_artifact_station()
returns trigger language plpgsql set search_path = '' as $$
declare lake_station_id uuid; snapshot_station_id uuid;
begin
  if tg_table_name = 'lake_data_sources' then
    select station_id into lake_station_id from public.lakes where lake_id = new.lake_id;
    if lake_station_id is distinct from new.station_id then
      raise exception 'lake data source station must own lake' using errcode = '23514';
    end if;
  elsif tg_table_name = 'risk_snapshots' then
    select station_id into lake_station_id from public.lakes where lake_id = new.lake_id;
    if lake_station_id is distinct from new.station_id then
      raise exception 'risk snapshot station must own lake' using errcode = '23514';
    end if;
  elsif tg_table_name = 'zone_plans' then
    select station_id into lake_station_id from public.lakes where lake_id = new.lake_id;
    select station_id into snapshot_station_id from public.risk_snapshots where snapshot_id = new.snapshot_id;
    if lake_station_id is distinct from new.station_id or snapshot_station_id is distinct from new.station_id then
      raise exception 'zone plan station must match lake and snapshot' using errcode = '23514';
    end if;
  end if;
  return new;
end;
$$;

create trigger lake_data_sources_station_matches_lake before insert on public.lake_data_sources
  for each row execute procedure private.assert_risk_artifact_station();
create trigger risk_snapshots_station_matches_lake before insert on public.risk_snapshots
  for each row execute procedure private.assert_risk_artifact_station();
create trigger zone_plans_station_matches_inputs before insert on public.zone_plans
  for each row execute procedure private.assert_risk_artifact_station();

create or replace function private.prevent_risk_artifact_mutation()
returns trigger language plpgsql set search_path = '' as $$
begin
  if current_setting('app.zone_plan_activation', true) = 'on'
    and tg_table_name = 'zone_plans'
    and tg_op = 'UPDATE'
    and old.status in ('validated', 'active')
    and new.status in ('active', 'superseded')
    and new.zone_plan_id = old.zone_plan_id
    and new.lake_id = old.lake_id
    and new.station_id = old.station_id
    and new.snapshot_id = old.snapshot_id
    and new.version = old.version
    and new.algorithm_version = old.algorithm_version
    and new.prior_plan_id is not distinct from old.prior_plan_id
  then return new; end if;
  raise exception '% is immutable', tg_table_name using errcode = '55000';
end;
$$;

create trigger socrata_connectors_immutable before update or delete on public.socrata_connectors
  for each row execute procedure private.prevent_risk_artifact_mutation();
create trigger lake_data_sources_immutable before update or delete on public.lake_data_sources
  for each row execute procedure private.prevent_risk_artifact_mutation();
create trigger risk_snapshots_immutable before update or delete on public.risk_snapshots
  for each row execute procedure private.prevent_risk_artifact_mutation();
create trigger zone_plans_immutable before update or delete on public.zone_plans
  for each row execute procedure private.prevent_risk_artifact_mutation();
create trigger zone_plan_cells_immutable before update or delete on public.zone_plan_cells
  for each row execute procedure private.prevent_risk_artifact_mutation();

create function public.activate_zone_plan(
  p_lake_id text, p_candidate_id uuid, p_expected_prior_id uuid
) returns boolean language plpgsql security definer set search_path = '' as $$
declare active_id uuid; candidate public.zone_plans%rowtype;
begin
  perform 1 from public.lakes where lake_id = p_lake_id for update;
  if not found then return false; end if;
  select zone_plan_id into active_id from public.zone_plans
    where lake_id = p_lake_id and status = 'active' for update;
  if active_id is distinct from p_expected_prior_id then return false; end if;
  select * into candidate from public.zone_plans
    where zone_plan_id = p_candidate_id and lake_id = p_lake_id for update;
  if not found or candidate.status <> 'validated' then return false; end if;
  perform set_config('app.zone_plan_activation', 'on', true);
  if active_id is not null then
    update public.zone_plans set status = 'superseded' where zone_plan_id = active_id;
  end if;
  update public.zone_plans set status = 'active', activated_at = now()
    where zone_plan_id = p_candidate_id;
  return true;
end;
$$;

alter table public.socrata_connectors enable row level security;
alter table public.socrata_connectors force row level security;
alter table public.lake_data_sources enable row level security;
alter table public.lake_data_sources force row level security;
alter table public.risk_snapshots enable row level security;
alter table public.risk_snapshots force row level security;
alter table public.zone_plans enable row level security;
alter table public.zone_plans force row level security;
alter table public.zone_plan_cells enable row level security;
alter table public.zone_plan_cells force row level security;

revoke all on public.socrata_connectors, public.lake_data_sources, public.risk_snapshots,
  public.zone_plans, public.zone_plan_cells from public, anon, authenticated;
grant select on public.socrata_connectors, public.lake_data_sources, public.risk_snapshots,
  public.zone_plans, public.zone_plan_cells to authenticated;

create policy socrata_connectors_select_station_member on public.socrata_connectors for select to authenticated
  using (exists (
    select 1 from public.lake_data_sources as source
    where source.connector_id = socrata_connectors.connector_id
      and private.is_active_station_member(auth.uid(), source.station_id)
  ));
create policy lake_data_sources_select_station_member on public.lake_data_sources for select to authenticated
  using (private.is_active_station_member(auth.uid(), station_id));
create policy risk_snapshots_select_station_member on public.risk_snapshots for select to authenticated
  using (private.is_active_station_member(auth.uid(), station_id));
create policy zone_plans_select_station_member on public.zone_plans for select to authenticated
  using (private.is_active_station_member(auth.uid(), station_id));
create policy zone_plan_cells_select_station_member on public.zone_plan_cells for select to authenticated
  using (exists (select 1 from public.zone_plans as plan where plan.zone_plan_id = zone_plan_cells.zone_plan_id
    and private.is_active_station_member(auth.uid(), plan.station_id)));

revoke all on function public.activate_zone_plan(text, uuid, uuid) from public, anon, authenticated;
grant execute on function public.activate_zone_plan(text, uuid, uuid) to service_role;
revoke all on function private.prevent_risk_artifact_mutation() from public, anon, authenticated;
revoke all on function private.assert_risk_artifact_station() from public, anon, authenticated;
