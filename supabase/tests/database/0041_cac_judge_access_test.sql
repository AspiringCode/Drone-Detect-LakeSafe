begin;
select plan(29);
select has_table('public','cac_judge_access','judge access allowlist exists');
select col_is_pk('public','cac_judge_access','user_id','one judge access row per user');
select fk_ok('public','cac_judge_access','user_id','auth','users','id','judge access references an Auth user');
select col_not_null('public','cac_judge_access','expires_at','judge access requires expiry');
select ok((select relrowsecurity and relforcerowsecurity from pg_class where oid='public.cac_judge_access'::regclass),'judge allowlist has forced RLS');
select table_privs_are('public','cac_judge_access','anon',array[]::text[],'anonymous browsers have no allowlist privileges');
select table_privs_are('public','cac_judge_access','authenticated',array[]::text[],'authenticated browsers have no allowlist privileges');
select table_privs_are('public','cac_judge_access','service_role',array['SELECT']::text[],'backend may only read judge allowlist');

insert into auth.users(id,aud,role,email,encrypted_password,email_confirmed_at,raw_app_meta_data,raw_user_meta_data,created_at,updated_at)
values
 ('00000000-0000-0000-0000-000000004101','authenticated','authenticated','judge-demo@example.test','not-used',now(),'{"fictional_demo":true,"fixture_set":"cac-2026-operators"}','{}',now(),now()),
 ('00000000-0000-0000-0000-000000004102','authenticated','authenticated','judge-anchor@example.test','not-used',now(),'{}','{}',now(),now()),
 ('00000000-0000-0000-0000-000000004103','authenticated','authenticated','judge-ordinary@example.test','not-used',now(),'{}','{}',now(),now());
select throws_ok($$insert into public.cac_judge_access(user_id,expires_at,created_at) values('00000000-0000-0000-0000-000000004101','2026-11-01T07:00:01Z','2026-10-01T00:00:00Z')$$,'23514',null,'judge access cannot extend beyond CAC cutoff');
select throws_ok($$insert into public.cac_judge_access(user_id,expires_at,created_at) values('00000000-0000-0000-0000-000000004101','2026-10-01T00:00:00Z','2026-10-01T00:00:00Z')$$,'23514',null,'judge expiry must be later than creation');
select throws_ok($$insert into public.cac_judge_access(user_id,expires_at,created_at) values('00000000-0000-0000-0000-000000004103','2026-11-01T07:00:00Z','2026-10-01T00:00:00Z')$$,'23514',null,'ordinary users cannot be provisioned as fictional CAC judges');
insert into public.cac_judge_access(user_id,expires_at,created_at)
values('00000000-0000-0000-0000-000000004101','2026-11-01T07:00:00Z','2026-10-01T00:00:00Z');
insert into public.officer_verifications(user_id,provider,provider_subject,method,affiliation,status,expires_at)
select id,'manual','judge-regression:'||id::text,'manual_review','us_law_enforcement','verified',now()+interval '1 day'
from auth.users where id in('00000000-0000-0000-0000-000000004101','00000000-0000-0000-0000-000000004102','00000000-0000-0000-0000-000000004103');
insert into public.stations(station_id,name,status) values
 ('00000000-0000-0000-0000-000000004111','Judge Station A','pending'),
 ('00000000-0000-0000-0000-000000004112','Judge Station B','pending');
insert into public.station_memberships(membership_id,station_id,user_id,status) values
 ('00000000-0000-0000-0000-000000004121','00000000-0000-0000-0000-000000004111','00000000-0000-0000-0000-000000004101','active'),
 ('00000000-0000-0000-0000-000000004122','00000000-0000-0000-0000-000000004111','00000000-0000-0000-0000-000000004102','active'),
 ('00000000-0000-0000-0000-000000004123','00000000-0000-0000-0000-000000004112','00000000-0000-0000-0000-000000004102','active'),
 ('00000000-0000-0000-0000-000000004124','00000000-0000-0000-0000-000000004111','00000000-0000-0000-0000-000000004103','active');
insert into public.station_membership_roles(membership_id,role) values
 ('00000000-0000-0000-0000-000000004121','station_admin'),
 ('00000000-0000-0000-0000-000000004122','station_admin'),
 ('00000000-0000-0000-0000-000000004123','station_admin'),
 ('00000000-0000-0000-0000-000000004124','viewer');
update public.stations set status='active' where station_id in('00000000-0000-0000-0000-000000004111','00000000-0000-0000-0000-000000004112');
set constraints all immediate;
insert into public.lakes(lake_id,station_id,name,centroid_lat,centroid_lon,shoreline,created_by)
values
 ('judge-lake-a','00000000-0000-0000-0000-000000004111','Judge Lake A',47.5,-122,public.st_geomfromtext('MULTIPOLYGON EMPTY',4326),'00000000-0000-0000-0000-000000004102'),
 ('judge-lake-b','00000000-0000-0000-0000-000000004112','Judge Lake B',47.5,-122,public.st_geomfromtext('MULTIPOLYGON EMPTY',4326),'00000000-0000-0000-0000-000000004102');
set local role authenticated;
select tests.authenticate_as('00000000-0000-0000-0000-000000004101','aal1');
select is((select count(*) from public.lakes where lake_id='judge-lake-a'),case when now()<'2026-11-01T07:00:00Z'::timestamptz then 1 else 0 end::bigint,'allowlisted AAL1 judge reads own lake only during the fixture window');
select is((select count(*) from public.lakes where lake_id='judge-lake-b'),0::bigint,'allowlisting does not grant cross-station scope');
select throws_ok($$select * from public.cac_judge_access$$,'42501',null,'browser cannot read judge allowlist');
select throws_ok($$insert into public.cac_judge_access(user_id,expires_at) values('00000000-0000-0000-0000-000000004103','2026-11-01T07:00:00Z')$$,'42501',null,'browser cannot grant judge access');
select throws_ok($$delete from public.cac_judge_access$$,'42501',null,'browser cannot revoke or alter judge access');
select throws_ok($$update public.lakes set name='blocked' where lake_id='judge-lake-a'$$,'42501',null,'judge bypass does not enable direct browser lake mutation');
select tests.authenticate_as('00000000-0000-0000-0000-000000004103','aal1');
select is((select count(*) from public.lakes where lake_id='judge-lake-a'),0::bigint,'ordinary AAL1 officer remains blocked');
select tests.authenticate_as('00000000-0000-0000-0000-000000004103','aal2');
select is((select count(*) from public.lakes where lake_id='judge-lake-a'),1::bigint,'ordinary AAL2 member remains allowed');
reset role;
update public.cac_judge_access set expires_at=least(now()-interval '1 second','2026-11-01T07:00:00Z'::timestamptz) where user_id='00000000-0000-0000-0000-000000004101';
set local role authenticated;
select tests.authenticate_as('00000000-0000-0000-0000-000000004101','aal1');
select is((select count(*) from public.lakes where lake_id='judge-lake-a'),0::bigint,'expired judge allowlist row cannot bypass AAL2');
reset role;
update public.cac_judge_access set expires_at='2026-11-01T07:00:00Z' where user_id='00000000-0000-0000-0000-000000004101';
delete from public.cac_judge_access where user_id='00000000-0000-0000-0000-000000004101';
set local role authenticated;
select is((select count(*) from public.lakes where lake_id='judge-lake-a'),0::bigint,'deleting allowlist row immediately revokes AAL1 bypass');
select tests.authenticate_as('00000000-0000-0000-0000-000000004101','aal2');
select is((select count(*) from public.lakes where lake_id='judge-lake-a'),1::bigint,'revoking judge bypass preserves normal AAL2 access');
reset role;
insert into public.cac_judge_access(user_id,expires_at,created_at) values('00000000-0000-0000-0000-000000004101','2026-11-01T07:00:00Z','2026-10-01T00:00:00Z');
update public.station_memberships set status='suspended' where membership_id='00000000-0000-0000-0000-000000004121';
set local role authenticated;
select tests.authenticate_as('00000000-0000-0000-0000-000000004101','aal1');
select is((select count(*) from public.lakes where lake_id='judge-lake-a'),0::bigint,'judge allowlist does not bypass suspended membership');
reset role;
update public.station_memberships set status='active' where membership_id='00000000-0000-0000-0000-000000004121';
update public.stations set status='suspended' where station_id='00000000-0000-0000-0000-000000004111';
set local role authenticated;
select is((select count(*) from public.lakes where lake_id='judge-lake-a'),0::bigint,'judge allowlist does not bypass suspended station');
reset role;
update public.stations set status='active' where station_id='00000000-0000-0000-0000-000000004111';
select private.transition_officer_verification(verification_id,'revoked') from public.officer_verifications where user_id='00000000-0000-0000-0000-000000004101';
set local role authenticated;
select is((select count(*) from public.lakes where lake_id='judge-lake-a'),0::bigint,'judge allowlist does not bypass revoked officer verification');
reset role;
set local role service_role;
select is((select count(*) from public.cac_judge_access where user_id='00000000-0000-0000-0000-000000004101'),1::bigint,'backend can read authoritative judge row');
select throws_ok($$delete from public.cac_judge_access$$,'42501',null,'backend service cannot provision or revoke judge rows');
reset role;
select ok((select prosecdef and proconfig && array['search_path=','search_path=""'] from pg_proc where oid='private.station_session_is_allowed()'::regprocedure),'session helper is definer with empty search path');
select ok(not has_function_privilege('authenticated','private.station_session_is_allowed()','EXECUTE'),'browser cannot execute judge helper directly');
select * from finish();
rollback;
