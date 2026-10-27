begin;
select plan(17);
select has_column('public','stations','simulation_only','stations declare physical isolation');
select has_column('public','lakes','demo_source_lake_id','demo lakes identify reviewed catalog source');
insert into auth.users(id,aud,role,email,encrypted_password,email_confirmed_at,raw_app_meta_data,raw_user_meta_data,created_at,updated_at)
values
 ('00000000-0000-0000-0000-000000005101','authenticated','authenticated','isolation-admin@example.test','not-used',now(),'{"fictional_demo":true,"fixture_set":"cac-2026-operators"}','{}',now(),now()),
 ('00000000-0000-0000-0000-000000005102','authenticated','authenticated','isolation-judge@example.test','not-used',now(),'{"fictional_demo":true,"fixture_set":"cac-2026-operators"}','{}',now(),now());
insert into public.cac_judge_access(user_id,expires_at)
values ('00000000-0000-0000-0000-000000005101','2027-01-01T08:00:00Z'),('00000000-0000-0000-0000-000000005102','2027-01-01T08:00:00Z');
insert into public.officer_verifications(user_id,provider,provider_subject,method,affiliation,status,expires_at)
select id,'manual','isolation:'||id::text,'manual_review','us_law_enforcement','verified','2027-01-01T08:00:00Z'
from auth.users where id in ('00000000-0000-0000-0000-000000005101','00000000-0000-0000-0000-000000005102');
insert into public.stations(station_id,name,status,simulation_only) values
 ('00000000-0000-0000-0000-000000005111','Isolated simulation','pending',true),
 ('00000000-0000-0000-0000-000000005112','Ordinary operations','pending',false);
insert into public.station_memberships(membership_id,station_id,user_id,status) values
 ('00000000-0000-0000-0000-000000005121','00000000-0000-0000-0000-000000005111','00000000-0000-0000-0000-000000005101','active'),
 ('00000000-0000-0000-0000-000000005122','00000000-0000-0000-0000-000000005112','00000000-0000-0000-0000-000000005101','active'),
 ('00000000-0000-0000-0000-000000005123','00000000-0000-0000-0000-000000005111','00000000-0000-0000-0000-000000005102','active'),
 ('00000000-0000-0000-0000-000000005124','00000000-0000-0000-0000-000000005112','00000000-0000-0000-0000-000000005102','active');
insert into public.station_membership_roles(membership_id,role) values
 ('00000000-0000-0000-0000-000000005121','station_admin'),('00000000-0000-0000-0000-000000005122','station_admin'),
 ('00000000-0000-0000-0000-000000005123','demo_operator'),('00000000-0000-0000-0000-000000005124','demo_operator');
update public.stations set status='active' where station_id in ('00000000-0000-0000-0000-000000005111','00000000-0000-0000-0000-000000005112');
insert into public.lakes(lake_id,station_id,name,centroid_lat,centroid_lon,shoreline,created_by)
values ('isolation-demo-lake','00000000-0000-0000-0000-000000005111','Demo lake',47.5,-122,public.st_geomfromtext('MULTIPOLYGON EMPTY',4326),'00000000-0000-0000-0000-000000005101'),
 ('isolation-real-lake','00000000-0000-0000-0000-000000005112','Real lake',47.5,-122,public.st_geomfromtext('MULTIPOLYGON EMPTY',4326),'00000000-0000-0000-0000-000000005101');
select throws_ok($$insert into public.drone_inventory(station_id,source,lifecycle) values('00000000-0000-0000-0000-000000005111','real','available')$$,'23514',null,'even privileged insertion cannot register a real drone in the demo station');
select lives_ok($$insert into public.drone_inventory(station_id,source,lifecycle) values('00000000-0000-0000-0000-000000005111','simulated','available')$$,'simulated inventory remains allowed');
select throws_ok($$update public.stations set simulation_only=false where station_id='00000000-0000-0000-0000-000000005111'$$,'23514',null,'simulation isolation cannot be removed');
select throws_ok($$update public.lakes set demo_source_lake_id='lake-beaver' where lake_id='isolation-real-lake'$$,'23514',null,'normal stations cannot request a demo runtime');
set constraints all immediate;
set local role authenticated;
select tests.authenticate_as('00000000-0000-0000-0000-000000005102','aal1');
select is((select count(*) from public.lakes where lake_id='isolation-demo-lake'),case when now()<'2027-01-01T08:00:00Z'::timestamptz then 1 else 0 end::bigint,'judge can read the isolated lake within the access window');
select is((select count(*) from public.lakes where lake_id='isolation-real-lake'),0::bigint,'demo role cannot read an ordinary station even if mistakenly assigned');
select is((select count(*) from public.drone_inventory where source='real'),0::bigint,'public judge sees no real inventory');
select throws_ok($$insert into public.station_membership_roles(membership_id,role) values('00000000-0000-0000-0000-000000005123','station_admin')$$,'42501',null,'public judge cannot grant administrator roles');
select throws_ok($$update public.stations set public_pages_open=true where station_id='00000000-0000-0000-0000-000000005111'$$,'42501',null,'public judge cannot publish station pages');
reset role;
select throws_ok($$update public.stations set demo_device_access=true where station_id='00000000-0000-0000-0000-000000005112'$$,'23514',null,'ordinary stations cannot opt in to public judge device access');
update public.stations set demo_device_access=true where station_id='00000000-0000-0000-0000-000000005111';
select lives_ok($$insert into public.drone_inventory(station_id,source,lifecycle) values('00000000-0000-0000-0000-000000005111','real','available')$$,'opted-in judge station can register devices');
insert into public.station_membership_roles(membership_id,role) values
 ('00000000-0000-0000-0000-000000005123','safety_supervisor'),('00000000-0000-0000-0000-000000005124','safety_supervisor');
select lives_ok($$select private.assert_real_safety_actor('00000000-0000-0000-0000-000000005111','00000000-0000-0000-0000-000000005102')$$,'judge can use fleet safety within the enabled demo station');
select throws_ok($$select private.assert_real_safety_actor('00000000-0000-0000-0000-000000005112','00000000-0000-0000-0000-000000005102')$$,'42501',null,'even a mistakenly assigned judge safety role cannot control an ordinary station');
select lives_ok($test$do $body$
declare registered jsonb; command jsonb;
begin
 registered:=public.register_real_drone('00000000-0000-0000-0000-000000005111','Test','PGTAP-JUDGE','AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA','00000000-0000-0000-0000-000000005102');
 update public.drone_inventory set lake_id='isolation-demo-lake',lifecycle='circulating' where inventory_id=(registered->>'drone_id')::uuid;
 command:=public.queue_real_patrol('00000000-0000-0000-0000-000000005111',(registered->>'drone_id')::uuid,'isolation-demo-lake','00000000-0000-0000-0000-000000005102',jsonb_build_object('lake_id','isolation-demo-lake','drone_id',registered->>'drone_id','mission','[[],[],[]]'::jsonb,'mission_hash',repeat('0',64)));
 if command is null then raise exception 'judge patrol queue denied'; end if;
end; $body$;$test$,'judge can queue reviewed patrols without station-management authority');
select throws_ok($$select public.queue_real_patrol('00000000-0000-0000-0000-000000005112','00000000-0000-0000-0000-000000005199','isolation-real-lake','00000000-0000-0000-0000-000000005102','{}')$$,'42501',null,'judge patrol queue rejects ordinary-station scope before device lookup');
select * from finish();
rollback;
