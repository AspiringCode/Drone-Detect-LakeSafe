-- Persist whether a lake was configured through a reviewed source contract or
-- authoritative fallback coverage.  No unreviewed dataset identifier is kept.
alter table public.lakes
  add column if not exists data_source_status text not null default 'fallback_coverage'
    check (data_source_status in ('reviewed', 'fallback_coverage'));

drop function if exists public.create_station_lake(text, uuid, text, double precision, double precision, jsonb, uuid);

create function public.create_station_lake(
  p_lake_id text, p_station_id uuid, p_name text, p_centroid_lat double precision,
  p_centroid_lon double precision, p_shoreline_geojson jsonb, p_created_by uuid,
  p_data_source_status text
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare lake_row public.lakes%rowtype;
begin
  if p_data_source_status not in ('reviewed', 'fallback_coverage') then
    raise exception 'invalid data source status' using errcode = '22023';
  end if;
  insert into public.lakes (
    lake_id, station_id, name, centroid_lat, centroid_lon, shoreline, created_by, data_source_status
  ) values (
    p_lake_id, p_station_id, p_name, p_centroid_lat, p_centroid_lon,
    st_multi(st_setsrid(st_geomfromgeojson(p_shoreline_geojson::text), 4326)), p_created_by,
    p_data_source_status
  ) returning * into lake_row;
  perform private.record_workflow_audit(p_created_by, p_station_id, p_lake_id,
    'lake.create', 'allowed', 'lake created', null,
    jsonb_build_object('lake_id', lake_row.lake_id, 'data_source_status', lake_row.data_source_status));
  return jsonb_build_object(
    'lake_id', lake_row.lake_id, 'station_id', lake_row.station_id,
    'name', lake_row.name, 'data_source_status', lake_row.data_source_status
  );
end;
$$;

revoke all on function public.create_station_lake(text, uuid, text, double precision, double precision, jsonb, uuid, text)
  from public, anon, authenticated;
grant execute on function public.create_station_lake(text, uuid, text, double precision, double precision, jsonb, uuid, text)
  to service_role;
