-- Native PostgreSQL assertions for the hosted CAC fixture deployment.
-- Every fixture, mutation, credential and audit event is rolled back.
begin;
do $$
declare
  actor uuid; other_actor uuid; station uuid; test_station uuid := gen_random_uuid();
  member uuid; target_member uuid; drone uuid := gen_random_uuid(); credential uuid;
  alert text := 'audit-rollback-' || gen_random_uuid()::text;
  result jsonb; payload jsonb; command uuid; second_command uuid;
  audit_count bigint;
begin
  select id into actor from auth.users where email='admin_master@lakesafe.example.test';
  select id into other_actor from auth.users where email='admin_ls@lakesafe.example.test';
  select station_id into station from public.lakes where lake_id='lake-sammamish';
  if actor is null or other_actor is null or station is null then raise exception 'CAC fixtures required'; end if;
  if has_function_privilege('anon','public.change_station_membership(uuid,uuid,uuid,text[],text)','execute')
    or has_function_privilege('authenticated','public.review_operational_alert(text,text,uuid)','execute')
    or has_function_privilege('authenticated','public.queue_real_patrol(uuid,uuid,text,uuid,jsonb)','execute')
    or has_table_privilege('anon','public.real_patrol_commands','select')
    or has_table_privilege('authenticated','public.real_patrol_commands','select') then
    raise exception 'privileged workflow exposed to client roles';
  end if;

  insert into public.stations(station_id,name,status) values(test_station,'Rollback-only audit station','active');
  insert into public.station_memberships(station_id,user_id,status) values(test_station,actor,'active') returning membership_id into member;
  insert into public.station_membership_roles(membership_id,role) values(member,'station_admin');
  insert into public.station_memberships(station_id,user_id,status) values(test_station,other_actor,'active') returning membership_id into target_member;
  insert into public.station_membership_roles(membership_id,role) values(target_member,'viewer');
  result := public.change_station_membership(test_station,target_member,actor,array['dispatcher'],'active');
  if result->'roles' <> '["dispatcher"]'::jsonb then raise exception 'member role update failed'; end if;
  if public.change_station_membership(station,target_member,actor,array['viewer'],'active') is not null then raise exception 'cross-station member update allowed'; end if;
  if public.change_station_membership(test_station,member,other_actor,array['viewer'],'active') is not null then raise exception 'non-admin member update allowed'; end if;
  begin
    perform public.change_station_membership(test_station,member,actor,array['viewer'],'active');
    raise exception 'last administrator was removed';
  exception when check_violation then null;
  end;
  if not exists(select 1 from public.station_membership_roles where membership_id=member and role='station_admin') then raise exception 'failed demotion was not atomic'; end if;

  insert into public.operational_alerts(alert_id,station_id,lake_id,occurred_at,precise_location,category,status,source)
    values(alert,station,'lake-sammamish',now(),st_geomfromtext('POINT(-122.09 47.61)',4326),'audit rollback','active','real');
  select count(*) into audit_count from public.audit_events where action='alert.review';
  result := public.review_operational_alert('lake-sammamish',alert,actor);
  if result->>'reviewed' <> 'true' or result->>'already_reviewed' <> 'false' then raise exception 'review not persisted'; end if;
  if public.review_operational_alert('lake-beaver',alert,actor) is not null then raise exception 'cross-lake review allowed'; end if;
  result := public.review_operational_alert('lake-sammamish',alert,actor);
  if result->>'already_reviewed' <> 'true' or (select count(*) from public.audit_events where action='alert.review') <> audit_count+1 then raise exception 'review is not idempotent'; end if;
  if (select status from public.operational_alerts where alert_id=alert) <> 'active' then raise exception 'review resolved an alert'; end if;

  insert into public.drone_inventory(inventory_id,station_id,lake_id,source,lifecycle) values(drone,station,'lake-sammamish','real','circulating');
  insert into public.drone_credentials(drone_id,station_id,manufacturer,serial,public_key,key_fingerprint)
    values(drone,station,'Rollback-only fixture',drone::text,repeat('A',43),replace(drone::text,'-','')||replace(gen_random_uuid()::text,'-','')) returning credential_id into credential;
  payload := jsonb_build_object('lake_id','lake-sammamish','drone_id',drone::text,'zone_id','audit-zone','mission_hash',repeat('a',64),
    'mission','[[0,16,0,0,0,0,47.61,-122.09,0],[3,22,0,0,0,0,47.61,-122.09,30],[2,20,0,0,0,0,0,0,0]]'::jsonb);
  result := public.queue_real_patrol(station,drone,'lake-sammamish',actor,payload);
  command := (result->>'command_id')::uuid;
  if command is null or result->>'status' <> 'queued' then raise exception 'patrol not queued'; end if;
  if public.queue_real_patrol(station,drone,'lake-sammamish',actor,payload) is not null then raise exception 'overlapping patrol accepted'; end if;
  result := public.deliver_real_patrols(drone,credential);
  if jsonb_array_length(result) <> 1 or result->0->>'patrol_ack' <> 'true' then raise exception 'patrol not delivered'; end if;
  if public.real_patrol_status(station,drone,command)->>'status' <> 'delivered' then raise exception 'delivery claimed upload'; end if;
  if not public.acknowledge_real_patrol(drone,credential,command,1,'accepted','test fixture upload') then raise exception 'valid upload acknowledgement rejected'; end if;
  if public.real_patrol_status(station,drone,command)->>'status' <> 'uploaded' then raise exception 'upload status missing'; end if;
  if public.acknowledge_real_patrol(drone,credential,command,1,'accepted','replay') then raise exception 'sequence replay accepted'; end if;
  if not public.acknowledge_real_patrol(drone,credential,command,2,'accepted','safe retry') then raise exception 'idempotent signed retry rejected'; end if;
  if public.acknowledge_real_patrol(drone,credential,command,3,'rejected','contrary outcome') then raise exception 'final upload outcome overwritten'; end if;

  result := public.queue_real_patrol(station,drone,'lake-sammamish',actor,payload);
  second_command := (result->>'command_id')::uuid;
  update public.real_patrol_commands set created_at=now()-interval '10 minutes',expires_at=now()-interval '1 minute' where command_id=second_command;
  if public.real_patrol_status(station,drone,second_command)->>'status' <> 'expired' then raise exception 'expired patrol still active'; end if;
  result := public.queue_real_patrol(station,drone,'lake-sammamish',actor,payload);
  second_command := (result->>'command_id')::uuid;
  update public.drone_inventory set lake_id=null,lifecycle='available' where inventory_id=drone;
  if jsonb_array_length(public.deliver_real_patrols(drone,credential)) <> 0 then raise exception 'detached drone received mission'; end if;
  if public.real_patrol_status(station,drone,second_command)->>'status' <> 'rejected' then raise exception 'detached mission not rejected'; end if;
  perform private.assert_station_has_verified_administrator(test_station);
end;
$$;
rollback;
select 'All native workflow assertions passed; fixtures rolled back' as result;
