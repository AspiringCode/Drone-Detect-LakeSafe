-- Public safety awareness is a projection, never a redacted operational row.
-- Keep the original import table for migration audit only.
alter table if exists public.alerts rename to legacy_alerts;

-- A legacy import is never a public fallback.  Keep it available only to a
-- service-side migration, with RLS forced even for table owners.
alter table public.legacy_alerts enable row level security;
alter table public.legacy_alerts force row level security;
revoke all on public.legacy_alerts from public, anon, authenticated;

create table if not exists public.legacy_alert_quarantine (
  alert_id text primary key,
  reason text not null,
  quarantined_at timestamptz not null default now()
);

create table public.operational_alerts (
  alert_id text primary key,
  station_id uuid not null references public.stations(station_id) on delete restrict,
  lake_id text not null references public.lakes(lake_id) on delete restrict,
  occurred_at timestamptz not null,
  precise_location geometry(Point, 4326) not null,
  category text not null,
  status text not null check (status in ('active','resolved','cancelled')),
  source text not null check (source in ('real','simulated')),
  hardware_ref text,
  serial_number text,
  battery numeric,
  health jsonb,
  maintenance_state text,
  connectivity_state text,
  evidence_ref text,
  thermal_clip_ref text,
  subject_data jsonb,
  response_tactics jsonb,
  created_at timestamptz not null default now()
);

create index operational_alerts_station_lake_idx on public.operational_alerts (station_id, lake_id, occurred_at desc);

create table public.public_lakes (
  lake_id text primary key references public.lakes(lake_id) on delete cascade,
  name text not null,
  approximate_center_geohash text,
  public_status text not null,
  refreshed_at timestamptz not null default now()
);

create table public.public_alerts (
  public_alert_id uuid primary key default gen_random_uuid(),
  operational_alert_id text not null unique references public.operational_alerts(alert_id) on delete cascade,
  lake_id text not null references public.lakes(lake_id) on delete cascade,
  category text not null,
  approximate_area_label text not null,
  public_status text not null,
  occurred_at timestamptz not null,
  published_at timestamptz not null,
  constraint public_alerts_minimum_delay check (published_at >= occurred_at + interval '5 minutes')
);

create table public.public_patrol_presence (
  public_patrol_presence_id uuid primary key default gen_random_uuid(),
  lake_id text not null references public.lakes(lake_id) on delete cascade,
  generalized_zone text not null,
  public_state text not null,
  observed_bucket timestamptz not null,
  published_at timestamptz not null,
  constraint public_patrol_presence_minimum_delay check (published_at >= observed_bucket + interval '5 minutes')
);

-- A legacy alert contains no trustworthy station/lake relation.  Quarantine it
-- instead of guessing.  A future reviewed migration may map confirmed IDs.
insert into public.legacy_alert_quarantine (alert_id, reason)
select alert_id, 'legacy alert lacks authoritative station and lake ownership'
from public.legacy_alerts
on conflict (alert_id) do nothing;

insert into public.public_lakes (lake_id, name, approximate_center_geohash, public_status, refreshed_at)
select lake_id, name, null, case when status = 'active' then 'available' else 'limited' end, now()
from public.lakes
on conflict (lake_id) do update set
  name = excluded.name,
  public_status = excluded.public_status,
  refreshed_at = excluded.refreshed_at;

alter table public.operational_alerts enable row level security;
alter table public.operational_alerts force row level security;
alter table public.public_lakes enable row level security;
alter table public.public_lakes force row level security;
alter table public.public_alerts enable row level security;
alter table public.public_alerts force row level security;
alter table public.public_patrol_presence enable row level security;
alter table public.public_patrol_presence force row level security;

revoke all on public.operational_alerts, public.public_lakes, public.public_alerts,
  public.public_patrol_presence, public.legacy_alert_quarantine from public, anon, authenticated;
grant select on public.public_lakes, public.public_alerts, public.public_patrol_presence to anon, authenticated;
grant select on public.operational_alerts to authenticated;

create policy operational_alerts_select_station_members
  on public.operational_alerts for select to authenticated
  using (private.is_active_station_member(auth.uid(), station_id));
create policy public_lakes_select_everyone on public.public_lakes for select to anon, authenticated using (true);
create policy public_alerts_select_everyone on public.public_alerts for select to anon, authenticated using (true);
create policy public_patrol_presence_select_everyone on public.public_patrol_presence for select to anon, authenticated using (true);
