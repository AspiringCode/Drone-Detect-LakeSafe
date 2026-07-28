-- A candidate is only visible as validated after its complete immutable cell
-- set has been inserted.  The lake row serializes per-lake version allocation.

create or replace function public.persist_validated_zone_plan(
  p_plan_id uuid,
  p_lake_id text,
  p_station_id uuid,
  p_snapshot_id uuid,
  p_prior_plan_id uuid,
  p_algorithm_version text,
  p_validation_payload jsonb,
  p_cells jsonb
) returns uuid language plpgsql security definer set search_path = '' as $$
declare
  lake_station_id uuid;
  snapshot_station_id uuid;
  next_version integer;
  cell jsonb;
  candidate_cell_count integer;
begin
  if jsonb_typeof(p_cells) <> 'array' or jsonb_array_length(p_cells) = 0 then
    raise exception 'candidate must include at least one cell' using errcode = '23514';
  end if;
  select station_id into lake_station_id from public.lakes
    where lake_id = p_lake_id for update;
  if not found or lake_station_id is distinct from p_station_id then
    raise exception 'station must own lake' using errcode = '23514';
  end if;
  select station_id into snapshot_station_id from public.risk_snapshots
    where snapshot_id = p_snapshot_id and lake_id = p_lake_id;
  if not found or snapshot_station_id is distinct from p_station_id then
    raise exception 'snapshot station must own lake' using errcode = '23514';
  end if;
  if p_prior_plan_id is not null and not exists (
    select 1 from public.zone_plans
      where zone_plan_id = p_prior_plan_id and lake_id = p_lake_id
  ) then
    raise exception 'prior plan does not belong to lake' using errcode = '23514';
  end if;
  select coalesce(max(version), 0) + 1 into next_version
    from public.zone_plans where lake_id = p_lake_id;
  insert into public.zone_plans (
    zone_plan_id, lake_id, station_id, snapshot_id, version, status,
    algorithm_version, prior_plan_id, validation_payload
  ) values (
    p_plan_id, p_lake_id, p_station_id, p_snapshot_id, next_version, 'validated',
    p_algorithm_version, p_prior_plan_id,
    coalesce(p_validation_payload, '{}'::jsonb) || jsonb_build_object('cell_count', jsonb_array_length(p_cells))
  );
  for cell in select value from jsonb_array_elements(p_cells) loop
    insert into public.zone_plan_cells (
      zone_plan_id, ordinal, kind, risk_score, seed, boundary, metadata
    ) values (
      p_plan_id,
      (cell->>'ordinal')::integer,
      cell->>'kind',
      (cell->>'risk_score')::double precision,
      public.st_setsrid(public.st_geomfromtext(cell->>'seed_wkt'), 4326),
      public.st_setsrid(public.st_geomfromtext(cell->>'boundary_wkt'), 4326),
      coalesce(cell->'metadata', '{}'::jsonb)
    );
  end loop;
  select count(*) into candidate_cell_count from public.zone_plan_cells
    where zone_plan_id = p_plan_id;
  if candidate_cell_count <> jsonb_array_length(p_cells) then
    raise exception 'candidate cell set is incomplete' using errcode = '23514';
  end if;
  return p_plan_id;
end;
$$;

create or replace function public.activate_zone_plan(
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
  if not found or candidate.status <> 'validated' or
    coalesce((candidate.validation_payload->>'cell_count')::integer, -1) <> (
      select count(*) from public.zone_plan_cells where zone_plan_id = p_candidate_id
    ) then return false; end if;
  perform set_config('app.zone_plan_activation', 'on', true);
  if active_id is not null then
    update public.zone_plans set status = 'superseded' where zone_plan_id = active_id;
  end if;
  update public.zone_plans set status = 'active', activated_at = now()
    where zone_plan_id = p_candidate_id;
  return true;
end;
$$;

revoke all on function public.persist_validated_zone_plan(uuid, text, uuid, uuid, uuid, text, jsonb, jsonb)
  from public, anon, authenticated;
grant execute on function public.persist_validated_zone_plan(uuid, text, uuid, uuid, uuid, text, jsonb, jsonb)
  to service_role;
