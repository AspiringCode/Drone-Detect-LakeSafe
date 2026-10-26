begin;
do $$
declare actor uuid; outsider uuid; source uuid; station uuid; lake text:='rollback-investigation-'||gen_random_uuid();
  first_drone uuid; second_drone uuid; credential uuid; command uuid; result jsonb; alert text:='rollback-alert-'||gen_random_uuid();
begin
  select id into actor from auth.users where email='admin_master@lakesafe.example.test';
  select id into outsider from auth.users where email='admin_ls@lakesafe.example.test';
  select station_id into source from public.lakes where lake_id='lake-sammamish';
  result:=public.create_lake_workspace(source,null,'Rollback investigation station',actor,lake,'Rollback lake',47.605,-122.095,
    '{"type":"MultiPolygon","coordinates":[[[[-122.1,47.6],[-122.1,47.61],[-122.09,47.61],[-122.09,47.6],[-122.1,47.6]]]]}');
  station:=(result->>'station_id')::uuid;
  insert into public.station_fleet_policies(station_id) values(station) on conflict do nothing;
  insert into public.real_fleet_safety_policies(station_id,lake_id,autonomy_state,updated_by) values(station,lake,'active',actor);
  insert into public.drone_inventory(station_id,lake_id,source,lifecycle) values(station,lake,'real','circulating') returning inventory_id into first_drone;
  insert into public.drone_inventory(station_id,lake_id,source,lifecycle) values(station,lake,'real','circulating') returning inventory_id into second_drone;
  -- Deliberately unusable public-only fixture, never a generated device private key.
  insert into public.drone_credentials(drone_id,station_id,manufacturer,serial,public_key,key_fingerprint)
    values(second_drone,station,'ROLLBACK',gen_random_uuid()::text,'unusable-test-key',gen_random_uuid()::text) returning credential_id into credential;
  insert into public.drone_heartbeats(drone_id,sequence,payload) values(second_drone,0,'{}');
  insert into public.operational_alerts(alert_id,station_id,lake_id,occurred_at,precise_location,category,status,source,hardware_ref)
    values(alert,station,lake,now(),public.st_geomfromtext('POINT(-122.095 47.605)',4326),'thermal-cv','active','real',first_drone::text);
  result:=public.begin_real_investigation(lake,alert,second_drone,'{"lat":47.606,"lon":-122.095}');
  if result->>'phase'<>'en_route' then raise exception 'second aircraft not tasked: %',result; end if;
  result:=public.deliver_investigation_commands(second_drone,credential);
  if jsonb_array_length(result)<>1 or result->0->>'command_type'<>'investigate' then raise exception 'investigate not delivered'; end if;
  command:=(result->0->>'command_id')::uuid;
  if not public.acknowledge_investigation_command(second_drone,credential,command,1,'accepted','Target requested') then raise exception 'ack failed'; end if;
  if (select finding from public.alert_investigations where alert_id=alert) is not null then raise exception 'arrival falsely corroborated'; end if;
  insert into public.operational_alerts(alert_id,station_id,lake_id,occurred_at,precise_location,category,status,source,hardware_ref)
    values(alert||'-second',station,lake,now(),public.st_geomfromtext('POINT(-122.095 47.605)',4326),'thermal-cv','active','real',second_drone::text);
  result:=public.begin_real_investigation(lake,alert||'-second',null,null);
  if result->>'corroborates'<>alert then raise exception 'independent report not associated'; end if;
  if (select finding from public.alert_investigations where alert_id=alert)<>'observed' then raise exception 'finding missing'; end if;
  if public.decide_operational_alert(lake,alert,outsider,'dismissed') is not null then raise exception 'cross station decision permitted'; end if;
  result:=public.decide_operational_alert(lake,alert,actor,'dismissed');
  if result->>'review_decision'<>'dismissed' then raise exception 'decision not durable'; end if;
  result:=public.deliver_investigation_commands(second_drone,credential);
  if jsonb_array_length(result)<>1 or result->0->>'command_type'<>'resume_patrol' then raise exception 'resume not delivered'; end if;
  command:=(result->0->>'command_id')::uuid;
  if not public.acknowledge_investigation_command(second_drone,credential,command,2,'accepted','Returning') then raise exception 'return ack failed'; end if;
  if not public.complete_real_investigation(second_drone,credential,2,alert) then raise exception 'return completion failed'; end if;
  if (select phase from public.alert_investigations where alert_id=alert)<>'returned' then raise exception 'completion missing'; end if;
  if public.acknowledge_investigation_command(second_drone,credential,command,2,'accepted','Replay') then raise exception 'replay accepted'; end if;
  perform public.set_station_public_visibility(station,actor,true);
  if not exists(select 1 from public.public_lakes where lake_id=lake and public_visible) then raise exception 'open not published'; end if;
  perform public.set_station_public_visibility(station,actor,false);
  if exists(select 1 from public.public_lakes where lake_id=lake and public_visible) then raise exception 'closed still visible'; end if;
  if has_function_privilege('authenticated','public.begin_real_investigation(text,text,uuid,jsonb)','execute')
    or has_function_privilege('anon','public.set_station_public_visibility(uuid,uuid,boolean)','execute') then raise exception 'privileged RPC exposed'; end if;
end; $$;
set local role anon;
do $$ begin
  if exists(select 1 from public.public_lakes where lake_id like 'rollback-investigation-%') then raise exception 'anonymous RLS bypass'; end if;
end; $$;
reset role;
select 'Investigation, decision, return, visibility and RLS assertions passed; fixtures rolled back.' as result;
rollback;
