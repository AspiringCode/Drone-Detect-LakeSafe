-- A crashed worker must not strand a lake.  Claims expire after ten minutes;
-- failures wait fifteen minutes before becoming claimable again.

alter table public.risk_refresh_jobs
  add column next_attempt_at timestamptz not null default now();

create function private.queue_initial_risk_refresh()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  insert into public.risk_refresh_jobs (lake_id, reason)
  values (new.lake_id, 'initial')
  on conflict (lake_id) do nothing;
  return new;
end;
$$;

create trigger lakes_queue_initial_risk_refresh
after insert on public.lakes for each row execute procedure private.queue_initial_risk_refresh();

create function private.initialize_risk_source_refresh_state()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  insert into public.risk_source_refresh_state (lake_data_source_id)
  values (new.lake_data_source_id)
  on conflict (lake_data_source_id) do nothing;
  return new;
end;
$$;

create trigger lake_data_sources_initialize_refresh_state
after insert on public.lake_data_sources for each row execute procedure private.initialize_risk_source_refresh_state();

insert into public.risk_refresh_jobs (lake_id, reason)
select lake.lake_id, 'initial' from public.lakes as lake
where not exists (select 1 from public.zone_plans as plan where plan.lake_id = lake.lake_id and plan.status = 'active')
on conflict (lake_id) do nothing;

insert into public.risk_source_refresh_state (lake_data_source_id)
select source.lake_data_source_id from public.lake_data_sources as source
on conflict (lake_data_source_id) do nothing;

create or replace function public.claim_queued_risk_refreshes(p_limit integer default 25)
returns table(lake_id text) language plpgsql security definer set search_path = '' as $$
begin
  return query
  with claimed as (
    select job.lake_id from public.risk_refresh_jobs as job
    where job.next_attempt_at <= now() and (
      job.status in ('queued', 'failed') or
      (job.status = 'processing' and job.claimed_at < now() - interval '10 minutes')
    )
    order by job.next_attempt_at, job.requested_at
    for update skip locked limit greatest(1, least(p_limit, 100))
  )
  update public.risk_refresh_jobs as job set status = 'processing', claimed_at = now()
  from claimed where job.lake_id = claimed.lake_id
  returning job.lake_id;
end;
$$;

create or replace function public.claim_due_risk_source_refreshes(p_limit integer default 25)
returns table(lake_id text) language plpgsql security definer set search_path = '' as $$
begin
  return query
  with claimed as (
    select state.lake_data_source_id, source.lake_id from public.risk_source_refresh_state as state
    join public.lake_data_sources as source using (lake_data_source_id)
    where state.next_refresh_at <= now() and (
      state.claimed_at is null or state.claimed_at < now() - interval '10 minutes'
    )
    order by state.next_refresh_at
    for update of state skip locked limit greatest(1, least(p_limit, 100))
  )
  update public.risk_source_refresh_state as state set claimed_at = now()
  from claimed where state.lake_data_source_id = claimed.lake_data_source_id
  returning claimed.lake_id;
end;
$$;

create or replace function public.fail_risk_refresh(p_lake_id text, p_reason text)
returns void language plpgsql security definer set search_path = '' as $$
begin
  update public.risk_refresh_jobs set status = 'failed', claimed_at = null,
    next_attempt_at = now() + interval '15 minutes',
    failure_reason = left(coalesce(nullif(p_reason, ''), 'unknown failure'), 500)
  where lake_id = p_lake_id;
  update public.risk_source_refresh_state as state set claimed_at = null,
    next_refresh_at = now() + interval '15 minutes',
    last_failure_reason = left(coalesce(nullif(p_reason, ''), 'unknown failure'), 500)
  from public.lake_data_sources as source
  where state.lake_data_source_id = source.lake_data_source_id and source.lake_id = p_lake_id;
end;
$$;

create or replace function public.complete_risk_refresh(p_lake_id text)
returns void language plpgsql security definer set search_path = '' as $$
declare cadence_hours integer;
begin
  update public.risk_refresh_jobs set status = 'complete', completed_at = now(), claimed_at = null,
    failure_reason = null where lake_id = p_lake_id;
  select coalesce(min(greatest(1, least(168, (connector.configuration->>'refresh_hours')::integer))), 24)
    into cadence_hours
  from public.lake_data_sources as source
  join public.socrata_connectors as connector on connector.connector_id = source.connector_id
  where source.lake_id = p_lake_id
    and coalesce(connector.configuration->>'refresh_hours', '') ~ '^[0-9]+$';
  update public.risk_source_refresh_state as state set claimed_at = null,
    next_refresh_at = now() + make_interval(hours => cadence_hours), last_failure_reason = null
  from public.lake_data_sources as source
  where state.lake_data_source_id = source.lake_data_source_id and source.lake_id = p_lake_id;
end;
$$;

create function public.risk_plan_rebuild_context(p_lake_id text)
returns jsonb language sql security definer set search_path = '' stable as $$
  select jsonb_build_object(
    'lake_id', lake.lake_id,
    'station_id', lake.station_id,
    'shoreline_wkt', public.st_astext(lake.shoreline),
    'data_source_status', lake.data_source_status,
    'patrol_capacity', lake.drone_inventory_cap,
    'safety_reserve', 0,
    'prior_plan_id', active.zone_plan_id,
    'sources', coalesce(sources.items, '[]'::jsonb)
  )
  from public.lakes as lake
  left join lateral (
    select plan.zone_plan_id from public.zone_plans as plan
    where plan.lake_id = lake.lake_id and plan.status = 'active'
  ) as active on true
  left join lateral (
    select jsonb_agg(jsonb_build_object(
      'connector_key', connector.connector_key, 'domain', connector.domain,
      'dataset_id', connector.dataset_id, 'schema_version', connector.schema_version
    ) order by connector.connector_key) as items
    from public.lake_data_sources as source
    join public.socrata_connectors as connector on connector.connector_id = source.connector_id
    where source.lake_id = lake.lake_id and connector.review_status = 'reviewed'
  ) as sources on true
  where lake.lake_id = p_lake_id;
$$;

create function public.persist_risk_snapshot(
  p_lake_id text, p_station_id uuid, p_status text, p_source_fresh_through timestamptz,
  p_source_metadata jsonb, p_canonical_payload text, p_payload_sha256 text, p_failure_reason text
) returns uuid language plpgsql security definer set search_path = '' as $$
declare snapshot_id uuid;
begin
  insert into public.risk_snapshots (
    lake_id, station_id, status, source_fresh_through, source_metadata,
    canonical_payload, payload_sha256, failure_reason
  ) values (
    p_lake_id, p_station_id, p_status, p_source_fresh_through,
    coalesce(p_source_metadata, '{}'::jsonb), p_canonical_payload::jsonb,
    p_payload_sha256, p_failure_reason
  ) on conflict (lake_id, payload_sha256) do nothing
  returning risk_snapshots.snapshot_id into snapshot_id;
  if snapshot_id is null then
    select value.snapshot_id into snapshot_id from public.risk_snapshots as value
    where value.lake_id = p_lake_id and value.payload_sha256 = p_payload_sha256;
  end if;
  return snapshot_id;
end;
$$;

revoke all on function public.risk_plan_rebuild_context(text),
  public.persist_risk_snapshot(text, uuid, text, timestamptz, jsonb, text, text, text) from public, anon, authenticated;
grant execute on function public.risk_plan_rebuild_context(text),
  public.persist_risk_snapshot(text, uuid, text, timestamptz, jsonb, text, text, text) to service_role;
