-- Publish only a coarse lake-area center for lakes already in the public catalog.
-- Five geohash characters describe an area roughly 5 km across, not telemetry.
create or replace function private.set_public_lake_location()
returns trigger language plpgsql set search_path = '' as $$
begin
  select public.st_geohash(public.st_setsrid(public.st_makepoint(lake.centroid_lon, lake.centroid_lat), 4326), 5)
  into new.approximate_center_geohash
  from public.lakes as lake where lake.lake_id = new.lake_id;
  return new;
end;
$$;

create trigger public_lake_location_on_publish
before insert or update on public.public_lakes
for each row execute function private.set_public_lake_location();

create or replace function private.refresh_public_lake_location()
returns trigger language plpgsql set search_path = '' as $$
begin
  update public.public_lakes set
    approximate_center_geohash = public.st_geohash(public.st_setsrid(public.st_makepoint(new.centroid_lon, new.centroid_lat), 4326), 5),
    refreshed_at = now()
  where lake_id = new.lake_id;
  return new;
end;
$$;

create trigger public_lake_location_on_move
after update of centroid_lat, centroid_lon on public.lakes
for each row when (old.centroid_lat is distinct from new.centroid_lat or old.centroid_lon is distinct from new.centroid_lon)
execute function private.refresh_public_lake_location();

revoke all on function private.set_public_lake_location(), private.refresh_public_lake_location() from public, anon, authenticated;

update public.public_lakes as projection set
  approximate_center_geohash = public.st_geohash(public.st_setsrid(public.st_makepoint(lake.centroid_lon, lake.centroid_lat), 4326), 5),
  refreshed_at = now()
from public.lakes as lake
where lake.lake_id = projection.lake_id;
