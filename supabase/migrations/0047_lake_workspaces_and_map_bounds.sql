alter table public.lakes add column map_bounds jsonb;
alter table public.public_lakes add column map_bounds jsonb;

create function private.set_lake_map_bounds() returns trigger
language plpgsql set search_path = '' as $$
begin
  new.map_bounds := case when public.st_isempty(new.shoreline) then null else
    jsonb_build_array(public.st_xmin(new.shoreline::public.box3d), public.st_ymin(new.shoreline::public.box3d),
                     public.st_xmax(new.shoreline::public.box3d), public.st_ymax(new.shoreline::public.box3d)) end;
  return new;
end;
$$;
create trigger lake_map_bounds before insert or update of shoreline on public.lakes
for each row execute function private.set_lake_map_bounds();
update public.lakes set map_bounds = case when public.st_isempty(shoreline) then null else
  jsonb_build_array(public.st_xmin(shoreline::public.box3d), public.st_ymin(shoreline::public.box3d),
                   public.st_xmax(shoreline::public.box3d), public.st_ymax(shoreline::public.box3d)) end;

create function private.set_public_map_bounds() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  select map_bounds into new.map_bounds from public.lakes where lake_id = new.lake_id;
  return new;
end;
$$;
create trigger public_map_bounds before insert or update on public.public_lakes
for each row execute function private.set_public_map_bounds();
create function private.refresh_published_map_bounds() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  update public.public_lakes set map_bounds = new.map_bounds where lake_id = new.lake_id;
  return new;
end;
$$;
create trigger published_map_bounds after update of map_bounds, shoreline on public.lakes
for each row execute function private.refresh_published_map_bounds();
update public.public_lakes as projection set map_bounds = lake.map_bounds
from public.lakes as lake where lake.lake_id = projection.lake_id;
revoke all on function private.set_lake_map_bounds(), private.set_public_map_bounds(),
  private.refresh_published_map_bounds() from public, anon, authenticated;

create function public.create_lake_workspace(
  p_source_station_id uuid, p_station_id uuid, p_new_station_name text, p_actor uuid,
  p_lake_id text, p_name text, p_lat double precision, p_lon double precision, p_shoreline jsonb
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  target_station uuid;
  new_membership uuid;
  lake_result jsonb;
  boundary public.geometry;
begin
  perform 1 from public.stations where station_id = p_source_station_id and status = 'active' for update;
  if not found or not exists (
    select 1 from public.station_memberships m
    join public.station_membership_roles r on r.membership_id = m.membership_id
    join public.officer_verifications v on v.user_id = m.user_id
    where m.station_id = p_source_station_id and m.user_id = p_actor and m.status = 'active'
      and r.role = 'station_admin' and private.officer_verification_is_current(v.verification_id)
  ) then raise exception 'active verified administrator required' using errcode = '42501'; end if;
  if (p_station_id is null) = (p_new_station_name is null)
    or (p_station_id is not null and p_station_id <> p_source_station_id)
    or length(trim(p_name)) not between 2 and 160
    or (p_new_station_name is not null and length(trim(p_new_station_name)) not between 2 and 160)
  then raise exception 'invalid lake destination' using errcode = '22023'; end if;
  boundary := public.st_multi(public.st_setsrid(public.st_geomfromgeojson(p_shoreline::text),4326));
  if not public.st_isvalid(boundary) or public.st_isempty(boundary)
    or public.geometrytype(boundary) <> 'MULTIPOLYGON'
    or not public.st_covers(boundary,public.st_setsrid(public.st_makepoint(p_lon,p_lat),4326))
  then raise exception 'invalid lake boundary' using errcode = '22023'; end if;
  if exists (select 1 from public.lakes l join public.stations s using (station_id)
    where lower(trim(l.name)) = lower(trim(p_name)) and public.st_equals(l.shoreline,boundary)
      and ((p_station_id is not null and l.station_id = p_station_id)
        or (p_station_id is null and l.created_by = p_actor and lower(trim(s.name)) = lower(trim(p_new_station_name)))))
  then raise exception 'lake already added' using errcode = '23505'; end if;
  target_station := p_station_id;
  if target_station is null then
    insert into public.stations(name,status) values(trim(p_new_station_name),'active') returning station_id into target_station;
    insert into public.station_memberships(station_id,user_id,status) values(target_station,p_actor,'active') returning membership_id into new_membership;
    insert into public.station_membership_roles(membership_id,role) values(new_membership,'station_admin');
    perform private.assert_station_has_verified_administrator(target_station);
    perform private.record_workflow_audit(p_actor,target_station,null,'station.create_for_lake','allowed',
      'administrator created a lake station',null,jsonb_build_object('source_station_id',p_source_station_id,'membership_id',new_membership));
  end if;
  lake_result := public.create_station_lake(p_lake_id,target_station,trim(p_name),p_lat,p_lon,p_shoreline,p_actor,'fallback_coverage');
  return lake_result || jsonb_build_object('station_created',new_membership is not null);
end;
$$;
revoke all on function public.create_lake_workspace(uuid,uuid,text,uuid,text,text,double precision,double precision,jsonb)
from public,anon,authenticated;
grant execute on function public.create_lake_workspace(uuid,uuid,text,uuid,text,text,double precision,double precision,jsonb) to service_role;
