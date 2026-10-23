begin;
select plan(10);
insert into auth.users(id,aud,role,email,encrypted_password,email_confirmed_at,raw_app_meta_data,raw_user_meta_data,created_at,updated_at)
values
 ('00000000-0000-0000-0000-000000004201','authenticated','authenticated','readonly-anchor@example.test','not-used',now(),'{}','{}',now(),now()),
 ('00000000-0000-0000-0000-000000004202','authenticated','authenticated','readonly-judge@example.test','not-used',now(),'{"fictional_demo":true,"fixture_set":"cac-2026-operators"}','{}',now(),now()),
 ('00000000-0000-0000-0000-000000004203','authenticated','authenticated','readonly-expired@example.test','not-used',now(),'{}','{}',now(),now()),
 ('00000000-0000-0000-0000-000000004204','authenticated','authenticated','readonly-revoked@example.test','not-used',now(),'{}','{}',now(),now());
insert into public.officer_verifications(user_id,provider,provider_subject,method,affiliation,status,expires_at,revoked_at)
values
 ('00000000-0000-0000-0000-000000004201','manual','readonly-anchor','manual_review','us_law_enforcement','verified',null,null),
 ('00000000-0000-0000-0000-000000004202','manual','readonly-judge','manual_review','us_law_enforcement','verified',now()+interval '1 day',null),
 ('00000000-0000-0000-0000-000000004203','manual','readonly-expired','manual_review','us_law_enforcement','verified',now()-interval '1 day',null),
 ('00000000-0000-0000-0000-000000004204','manual','readonly-revoked','manual_review','us_law_enforcement','verified',now()+interval '1 day',now());
insert into public.cac_judge_access(user_id,created_at,expires_at)
values('00000000-0000-0000-0000-000000004202','2026-10-01T00:00:00Z','2026-11-01T07:00:00Z');
insert into public.stations(station_id,name,status) values
 ('00000000-0000-0000-0000-000000004211','Read-only Station A','pending'),
 ('00000000-0000-0000-0000-000000004212','Read-only Station B','pending');
insert into public.station_memberships(membership_id,station_id,user_id,status) values
 ('00000000-0000-0000-0000-000000004221','00000000-0000-0000-0000-000000004211','00000000-0000-0000-0000-000000004201','active'),
 ('00000000-0000-0000-0000-000000004222','00000000-0000-0000-0000-000000004212','00000000-0000-0000-0000-000000004201','active'),
 ('00000000-0000-0000-0000-000000004223','00000000-0000-0000-0000-000000004211','00000000-0000-0000-0000-000000004202','active'),
 ('00000000-0000-0000-0000-000000004224','00000000-0000-0000-0000-000000004211','00000000-0000-0000-0000-000000004203','active'),
 ('00000000-0000-0000-0000-000000004225','00000000-0000-0000-0000-000000004211','00000000-0000-0000-0000-000000004204','active');
insert into public.station_membership_roles(membership_id,role) values
 ('00000000-0000-0000-0000-000000004221','station_admin'),
 ('00000000-0000-0000-0000-000000004222','station_admin'),
 ('00000000-0000-0000-0000-000000004223','viewer'),
 ('00000000-0000-0000-0000-000000004224','viewer'),
 ('00000000-0000-0000-0000-000000004225','viewer');
update public.stations set status='active' where station_id in('00000000-0000-0000-0000-000000004211','00000000-0000-0000-0000-000000004212');
set constraints all immediate;
insert into public.lakes(lake_id,station_id,name,centroid_lat,centroid_lon,shoreline,created_by) values
 ('readonly-lake-a','00000000-0000-0000-0000-000000004211','Read-only Lake A',47.5,-122,public.st_geomfromtext('MULTIPOLYGON EMPTY',4326),'00000000-0000-0000-0000-000000004201'),
 ('readonly-lake-b','00000000-0000-0000-0000-000000004212','Read-only Lake B',47.5,-122,public.st_geomfromtext('MULTIPOLYGON EMPTY',4326),'00000000-0000-0000-0000-000000004201');
-- Complete pgTAP bookkeeping before entering real read-only mode below.
set local role authenticated;
select tests.authenticate_as('00000000-0000-0000-0000-000000004201','aal2');
select lives_ok($$select lake_id from public.lakes where lake_id='readonly-lake-a'$$,'ordinary AAL2 station read succeeds before read-only probe');
select is((select count(*) from public.lakes where lake_id='readonly-lake-a'),1::bigint,'unexpired verification with no expiry retains normal station access');
select tests.authenticate_as('00000000-0000-0000-0000-000000004202','aal1');
select is((select count(*) from public.lakes where lake_id='readonly-lake-a'),case when now()<'2026-11-01T07:00:00Z'::timestamptz then 1 else 0 end::bigint,'current judge AAL1 session reads own lake');
select is((select count(*) from public.lakes where lake_id='readonly-lake-b'),0::bigint,'judge session cannot read a different station');
select tests.authenticate_as('00000000-0000-0000-0000-000000004201','aal1');
select is((select count(*) from public.lakes where lake_id='readonly-lake-a'),0::bigint,'ordinary AAL1 remains denied');
select tests.authenticate_as('00000000-0000-0000-0000-000000004203','aal2');
select is((select count(*) from public.lakes where lake_id='readonly-lake-a'),0::bigint,'expired verification denies access without attempting maintenance');
select tests.authenticate_as('00000000-0000-0000-0000-000000004204','aal2');
select is((select count(*) from public.lakes where lake_id='readonly-lake-a'),0::bigint,'revoked_at denies access even when status still says verified');
reset role;
select is((select status from public.officer_verifications where user_id='00000000-0000-0000-0000-000000004203'),'verified','RLS expiry evaluation leaves historical verification status unchanged');
select is((select version from public.officer_verifications where user_id='00000000-0000-0000-0000-000000004203'),0::bigint,'RLS expiry evaluation does not increment verification version');
select is((select status from public.stations where station_id='00000000-0000-0000-0000-000000004211'),'active','RLS expiry evaluation does not mutate station state');
select * from finish();
-- No pgTAP calls, table creation or persistent writes after this point.
set local transaction_read_only=on;
do $readonly$
declare probe record; actual bigint;
begin
 for probe in
   select * from (values
     ('00000000-0000-0000-0000-000000004201'::uuid,'aal2','readonly-lake-a',1::bigint),
     ('00000000-0000-0000-0000-000000004202'::uuid,'aal1','readonly-lake-a',case when now()<'2026-11-01T07:00:00Z'::timestamptz then 1 else 0 end::bigint),
     ('00000000-0000-0000-0000-000000004202'::uuid,'aal1','readonly-lake-b',0::bigint),
     ('00000000-0000-0000-0000-000000004201'::uuid,'aal1','readonly-lake-a',0::bigint),
     ('00000000-0000-0000-0000-000000004203'::uuid,'aal2','readonly-lake-a',0::bigint),
     ('00000000-0000-0000-0000-000000004204'::uuid,'aal2','readonly-lake-a',0::bigint)
   ) as expected(user_id,aal,lake_id,row_count)
 loop
   perform set_config('request.jwt.claims',jsonb_build_object('sub',probe.user_id,'role','authenticated','aal',probe.aal)::text,true);
   perform set_config('request.jwt.claim.sub',probe.user_id::text,true);
   perform set_config('request.jwt.claim.aal',probe.aal,true);
   execute 'set local role authenticated';
   select count(*) into actual from public.lakes where lake_id=probe.lake_id;
   execute 'reset role';
   if actual<>probe.row_count then
     raise exception 'Read-only station policy mismatch for % %: expected %, actual %',probe.user_id,probe.aal,probe.row_count,actual;
   end if;
 end loop;
 if (select status from public.officer_verifications where user_id='00000000-0000-0000-0000-000000004203')<>'verified'
 or (select version from public.officer_verifications where user_id='00000000-0000-0000-0000-000000004203')<>0 then
   raise exception 'Read-only station policy changed expired verification state';
 end if;
 raise notice 'PASS: six actual read-only policy probes and unchanged expiry state';
end;
$readonly$;
rollback;
