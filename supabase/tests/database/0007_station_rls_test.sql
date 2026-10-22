begin;

select plan(29);

insert into auth.users (id, aud, role, email, encrypted_password, email_confirmed_at, raw_app_meta_data, raw_user_meta_data, created_at, updated_at)
values
  ('00000000-0000-0000-0000-000000000601', 'authenticated', 'authenticated', 'station-a-admin@example.test', 'not-used', now(), '{}'::jsonb, '{}'::jsonb, now(), now()),
  ('00000000-0000-0000-0000-000000000602', 'authenticated', 'authenticated', 'station-a-member@example.test', 'not-used', now(), '{}'::jsonb, '{}'::jsonb, now(), now()),
  ('00000000-0000-0000-0000-000000000603', 'authenticated', 'authenticated', 'station-b-admin@example.test', 'not-used', now(), '{}'::jsonb, '{}'::jsonb, now(), now()),
  ('00000000-0000-0000-0000-000000000604', 'authenticated', 'authenticated', 'expiring-admin@example.test', 'not-used', now(), '{}'::jsonb, '{}'::jsonb, now(), now());

insert into public.officer_verifications (user_id, provider, provider_subject, method, affiliation, status, expires_at)
values
  ('00000000-0000-0000-0000-000000000601', 'manual', 'rls-a-admin', 'manual_review', 'us_law_enforcement', 'verified', now() + interval '1 day'),
  ('00000000-0000-0000-0000-000000000602', 'manual', 'rls-a-member', 'manual_review', 'us_law_enforcement', 'verified', now() + interval '1 day'),
  ('00000000-0000-0000-0000-000000000603', 'manual', 'rls-b-admin', 'manual_review', 'us_law_enforcement', 'verified', now() + interval '1 day'),
  ('00000000-0000-0000-0000-000000000604', 'manual', 'rls-expiring-admin', 'manual_review', 'us_law_enforcement', 'verified', now() - interval '1 minute');

insert into public.stations (station_id, name, status) values
  ('00000000-0000-0000-0000-000000000611', 'RLS A', 'pending'),
  ('00000000-0000-0000-0000-000000000612', 'RLS B', 'pending'),
  ('00000000-0000-0000-0000-000000000613', 'Expiry station', 'pending');
insert into public.station_memberships (membership_id, station_id, user_id, status) values
  ('00000000-0000-0000-0000-000000000621', '00000000-0000-0000-0000-000000000611', '00000000-0000-0000-0000-000000000601', 'active'),
  ('00000000-0000-0000-0000-000000000622', '00000000-0000-0000-0000-000000000611', '00000000-0000-0000-0000-000000000602', 'active'),
  ('00000000-0000-0000-0000-000000000623', '00000000-0000-0000-0000-000000000612', '00000000-0000-0000-0000-000000000603', 'active'),
  ('00000000-0000-0000-0000-000000000624', '00000000-0000-0000-0000-000000000613', '00000000-0000-0000-0000-000000000604', 'active');
insert into public.station_membership_roles (membership_id, role) values
  ('00000000-0000-0000-0000-000000000621', 'station_admin'),
  ('00000000-0000-0000-0000-000000000622', 'viewer'),
  ('00000000-0000-0000-0000-000000000623', 'station_admin'),
  ('00000000-0000-0000-0000-000000000624', 'station_admin');
update public.stations set status = 'active' where station_id in ('00000000-0000-0000-0000-000000000611', '00000000-0000-0000-0000-000000000612');
update public.stations set status = 'active' where station_id = '00000000-0000-0000-0000-000000000613';
select ok(
  not private.officer_verification_is_current((select verification_id from public.officer_verifications where user_id = '00000000-0000-0000-0000-000000000604')),
  'expired final administrator is demoted without a constraint failure'
);
select is((select status from public.stations where station_id = '00000000-0000-0000-0000-000000000613'), 'suspended', 'expiry suspends an otherwise-adminless active station');
set constraints all immediate;
insert into public.lakes (lake_id, org_id, name, centroid_lat, centroid_lon, station_id, shoreline, status, created_by)
values
  ('rls-lake-a', 'org-demo', 'RLS Lake A', 47.5, -122.0, '00000000-0000-0000-0000-000000000611', st_multi(st_geomfromtext('MULTIPOLYGON EMPTY', 4326)), 'draft', '00000000-0000-0000-0000-000000000601'),
  ('rls-lake-b', 'org-demo', 'RLS Lake B', 47.6, -122.1, '00000000-0000-0000-0000-000000000612', st_multi(st_geomfromtext('MULTIPOLYGON EMPTY', 4326)), 'draft', '00000000-0000-0000-0000-000000000603');

set local role authenticated;
select tests.authenticate_as('00000000-0000-0000-0000-000000000602'::uuid, 'aal1');
select is((select count(*) from public.lakes where lake_id = 'rls-lake-a'), 0::bigint, 'AAL1 cannot read station lakes');

select tests.authenticate_as('00000000-0000-0000-0000-000000000602'::uuid, 'aal2');
select lives_ok($$ select lake_id from public.lakes where lake_id = 'rls-lake-a' $$, 'authenticated policy helper evaluation does not recurse under forced RLS');
select is((select count(*) from public.lakes where lake_id = 'rls-lake-a'), 1::bigint, 'active verified member reads own station lake');
select is((select count(*) from public.lakes where lake_id = 'rls-lake-b'), 0::bigint, 'cross-station lake select is empty');
select is((select count(*) from public.stations where station_id = '00000000-0000-0000-0000-000000000612'), 0::bigint, 'cross-station station select is empty');
select is((select count(*) from public.station_memberships where station_id = '00000000-0000-0000-0000-000000000612'), 0::bigint, 'cross-station membership select is empty');
select is((select count(*) from public.station_membership_roles where membership_id = '00000000-0000-0000-0000-000000000623'), 0::bigint, 'cross-station role select is empty');
select throws_ok($$ update public.lakes set name = 'blocked' where lake_id = 'rls-lake-a' $$, '42501', null, 'non-admin lake mutation is denied');
select throws_ok($$ update public.lakes set name = 'blocked' where lake_id = 'rls-lake-b' $$, '42501', null, 'cross-station lake mutation is denied');
select throws_ok($$ update public.stations set name = 'blocked' where station_id = '00000000-0000-0000-0000-000000000612' $$, '42501', null, 'cross-station station mutation is denied');
select throws_ok($$ update public.station_memberships set status = 'revoked' where membership_id = '00000000-0000-0000-0000-000000000623' $$, '42501', null, 'cross-station membership mutation is denied');
select throws_ok($$ insert into public.station_invitations (station_id, token_hash, intended_email, expires_at) values ('00000000-0000-0000-0000-000000000612', repeat('b', 64), 'blocked@example.test', now() + interval '1 day') $$, '42501', null, 'cross-station invitation creation is denied');
select throws_ok($$ insert into public.station_join_requests (station_id, user_id) values ('00000000-0000-0000-0000-000000000612', '00000000-0000-0000-0000-000000000602') $$, '42501', null, 'cross-station join-request creation is denied');
select throws_ok($$ update public.organizations set name = 'blocked' where org_id = 'org-demo' $$, '42501', null, 'legacy organizations cannot be mutated by a client');
select throws_ok($$ insert into public.station_membership_roles (membership_id, role) values ('00000000-0000-0000-0000-000000000622', 'station_admin') $$, '42501', null, 'clients cannot self-assign roles');
select throws_ok($$ update public.officer_verifications set status = 'verified' where user_id = '00000000-0000-0000-0000-000000000602' $$, '42501', null, 'clients cannot mutate verification');

select tests.authenticate_as('00000000-0000-0000-0000-000000000601'::uuid, 'aal2');
select throws_ok($$ update public.lakes set name = 'admin update' where lake_id = 'rls-lake-a' $$, '42501', null, 'browser station admins cannot update lakes directly');

reset role;
select ok((select relrowsecurity and relforcerowsecurity from pg_class where oid = 'public.lakes'::regclass), 'lakes use forced RLS');
select ok((select relrowsecurity and relforcerowsecurity from pg_class where oid = 'public.organizations'::regclass), 'legacy organizations use forced RLS');
select ok(has_function_privilege('authenticated', 'private.has_station_role(uuid,text[])', 'execute'), 'only the safe station capability helper is exposed for RLS evaluation');

select function_privs_are('public', 'create_station_lake', array['text', 'uuid', 'text', 'double precision', 'double precision', 'jsonb', 'uuid', 'text'], 'anon', array[]::text[], 'anonymous browsers cannot execute lake creation');
select function_privs_are('public', 'create_station_lake', array['text', 'uuid', 'text', 'double precision', 'double precision', 'jsonb', 'uuid', 'text'], 'authenticated', array[]::text[], 'authenticated browsers cannot execute lake creation');
select col_not_null('public', 'lakes', 'station_id', 'station ownership remains mandatory for new lakes');
select fk_ok('public', 'lakes', 'station_id', 'public', 'stations', 'station_id', 'new lakes retain their station foreign key');
set local role service_role;
select lives_ok(
  $$ select public.create_station_lake(
    'rls-created-lake', '00000000-0000-0000-0000-000000000611'::uuid,
    'Backend Created Lake', 47.5, -122.0,
    '{"type":"Polygon","coordinates":[[[-122.01,47.49],[-121.99,47.49],[-121.99,47.51],[-122.01,47.49]]]}'::jsonb,
    '00000000-0000-0000-0000-000000000601'::uuid, 'fallback_coverage'
  ) $$,
  'service role creates a station lake with the pinned function search path'
);
select is(
  (select station_id from public.lakes where lake_id = 'rls-created-lake'),
  '00000000-0000-0000-0000-000000000611'::uuid,
  'created lake belongs to the requested station'
);
select ok(
  (select lake.org_id is null and station.legacy_org_id is null
   from public.lakes lake join public.stations station on station.station_id = lake.station_id
   where lake.lake_id = 'rls-created-lake'),
  'a station without a legacy organization can own a new lake'
);
reset role;

select * from finish();
rollback;
