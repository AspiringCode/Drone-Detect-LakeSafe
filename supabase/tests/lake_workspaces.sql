-- Disposable assertions: no station, lake, membership or publication is retained.
begin;
do $$
declare
  actor uuid; other_actor uuid; source uuid; station uuid; result jsonb;
  lake text := 'rollback-lake-' || gen_random_uuid()::text;
  boundary jsonb := '{"type":"MultiPolygon","coordinates":[[[[-122.1,47.6],[-122.1,47.61],[-122.09,47.61],[-122.09,47.6],[-122.1,47.6]]]]}';
  before_count integer;
begin
  select id into actor from auth.users where email='admin_master@lakesafe.example.test';
  select id into other_actor from auth.users where email='admin_ls@lakesafe.example.test';
  select station_id into source from public.lakes where lake_id='lake-sammamish';
  if actor is null or other_actor is null or source is null then raise exception 'CAC fixtures required'; end if;
  if has_function_privilege('authenticated','public.create_lake_workspace(uuid,uuid,text,uuid,text,text,double precision,double precision,jsonb)','execute')
    or has_function_privilege('anon','public.create_lake_workspace(uuid,uuid,text,uuid,text,text,double precision,double precision,jsonb)','execute')
  then raise exception 'client access to privileged RPC'; end if;
  result := public.create_lake_workspace(source,null,'Rollback-only lake station',actor,lake,'Rollback-only lake',47.605,-122.095,boundary);
  station := (result->>'station_id')::uuid;
  if result->>'station_created' <> 'true' then raise exception 'station not created'; end if;
  if not exists(select 1 from public.station_memberships m join public.station_membership_roles r using(membership_id)
    where m.station_id=station and m.user_id=actor and m.status='active' and r.role='station_admin')
  then raise exception 'creator not administrator'; end if;
  if (select count(*) from public.station_memberships where station_id=station) <> 1 then raise exception 'unexpected member grant'; end if;
  if not exists(select 1 from public.risk_refresh_jobs where lake_id=lake and status='queued') then raise exception 'setup not queued'; end if;
  if exists(select 1 from public.public_lakes where lake_id=lake) then raise exception 'unrequested public publication'; end if;
  if (select map_bounds from public.lakes where lake_id=lake) <> '[-122.1,47.6,-122.09,47.61]'::jsonb then raise exception 'incorrect bounds'; end if;
  insert into public.public_lakes(lake_id,name,public_status) values(lake,'Rollback-only lake','available');
  if (select map_bounds from public.public_lakes where lake_id=lake) <> '[-122.1,47.6,-122.09,47.61]'::jsonb then raise exception 'public bounds not projected'; end if;
  begin
    perform public.create_lake_workspace(station,station,null,other_actor,lake||'-denied','Unauthorized lake',47.605,-122.095,boundary);
    raise exception 'unowned station allowed';
  exception when insufficient_privilege then null; end;
  begin
    perform public.create_lake_workspace(source,station,null,actor,lake||'-cross','Cross station',47.605,-122.095,boundary);
    raise exception 'mismatched authority allowed';
  exception when invalid_parameter_value then null; end;
  select count(*) into before_count from public.stations;
  begin
    perform public.create_lake_workspace(source,null,'Rollback-only lake station',actor,lake||'-duplicate','Rollback-only lake',47.605,-122.095,boundary);
    raise exception 'duplicate lake station allowed';
  exception when unique_violation then null; end;
  if (select count(*) from public.stations) <> before_count then raise exception 'duplicate left a station'; end if;
  begin
    perform public.create_lake_workspace(source,null,'Invalid boundary station',actor,lake||'-bad','Invalid lake',47.605,-122.095,'{"type":"MultiPolygon","coordinates":[]}');
    raise exception 'empty boundary allowed';
  exception when invalid_parameter_value then null; end;
  if (select count(*) from public.stations) <> before_count then raise exception 'invalid lake left a station'; end if;
  result := public.create_lake_workspace(station,station,null,actor,lake||'-existing','Second lake',47.605,-122.095,boundary);
  if result->>'station_created' <> 'false' or (result->>'station_id')::uuid <> station then raise exception 'existing destination incorrect'; end if;
end;
$$;
select 'Lake workspace assertions passed; all fixtures rolled back.' as result;
rollback;
