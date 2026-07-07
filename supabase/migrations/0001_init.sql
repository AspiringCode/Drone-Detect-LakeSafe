create table if not exists alerts (
  alert_id text primary key,
  created_at timestamptz not null,
  location jsonb not null,
  detection_mode text not null,
  drone_id text not null,
  thermal_clip_ref text,
  confirmed boolean not null,
  source text not null check (source in ('real', 'simulated')),
  latency_ms integer
);

create table if not exists detection_events (
  event_id text primary key,
  created_at timestamptz not null,
  frame_idx integer not null,
  bbox jsonb not null,
  confidence double precision not null,
  source text not null check (source in ('real', 'simulated'))
);

insert into storage.buckets (id, name, public)
values ('thermal-clips', 'thermal-clips', false)
on conflict (id) do nothing;
