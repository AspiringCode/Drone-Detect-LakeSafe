begin;

select plan(36);

select has_table('public', 'stations', 'stations table exists');
select has_table('public', 'station_requests', 'station requests table exists');
select has_table('public', 'station_memberships', 'station memberships table exists');
select has_table('public', 'station_membership_roles', 'station membership roles table exists');
select has_table('public', 'station_invitations', 'station invitations table exists');
select has_table('public', 'station_join_requests', 'station join requests table exists');
select ok(exists (select 1 from pg_constraint c join pg_attribute a on a.attrelid = c.conrelid and a.attnum = any(c.conkey) where c.conrelid = 'public.stations'::regclass and c.contype = 'c' and a.attname = 'status'), 'station status is constrained');
select ok(exists (select 1 from pg_constraint c join pg_attribute a on a.attrelid = c.conrelid and a.attnum = any(c.conkey) where c.conrelid = 'public.station_memberships'::regclass and c.contype = 'c' and a.attname = 'status'), 'membership status is constrained');
select ok(exists (select 1 from pg_constraint c join pg_attribute a on a.attrelid = c.conrelid and a.attnum = any(c.conkey) where c.conrelid = 'public.station_membership_roles'::regclass and c.contype = 'c' and a.attname = 'role'), 'station role is constrained');
select ok(exists (select 1 from pg_constraint c join pg_attribute a on a.attrelid = c.conrelid and a.attnum = any(c.conkey) where c.conrelid = 'public.station_join_requests'::regclass and c.contype = 'c' and a.attname = 'status'), 'join request status is constrained');
select col_is_unique('public', 'station_invitations', array['token_hash'], 'invitation token hashes are unique');

insert into auth.users (id, aud, role, email, encrypted_password, email_confirmed_at, raw_app_meta_data, raw_user_meta_data, created_at, updated_at)
values
  ('00000000-0000-0000-0000-000000000301', 'authenticated', 'authenticated', 'admin@example.test', 'not-used', now(), '{}'::jsonb, '{}'::jsonb, now(), now()),
  ('00000000-0000-0000-0000-000000000302', 'authenticated', 'authenticated', 'member@example.test', 'not-used', now(), '{}'::jsonb, '{}'::jsonb, now(), now()),
  ('00000000-0000-0000-0000-000000000303', 'authenticated', 'authenticated', 'unassigned@example.test', 'not-used', now(), '{}'::jsonb, '{}'::jsonb, now(), now()),
  ('00000000-0000-0000-0000-000000000304', 'authenticated', 'authenticated', 'expired@example.test', 'not-used', now(), '{}'::jsonb, '{}'::jsonb, now(), now()),
  ('00000000-0000-0000-0000-000000000305', 'authenticated', 'authenticated', 'moved-admin@example.test', 'not-used', now(), '{}'::jsonb, '{}'::jsonb, now(), now());

insert into public.officer_verifications (user_id, provider, provider_subject, method, affiliation, status, expires_at)
values
  ('00000000-0000-0000-0000-000000000301', 'manual', 'station-admin-301', 'manual_review', 'us_law_enforcement', 'verified', now() + interval '1 day'),
  ('00000000-0000-0000-0000-000000000302', 'manual', 'station-member-302', 'manual_review', 'us_law_enforcement', 'verified', now() + interval '1 day'),
  ('00000000-0000-0000-0000-000000000303', 'manual', 'station-unassigned-303', 'manual_review', 'us_law_enforcement', 'verified', now() + interval '1 day'),
  ('00000000-0000-0000-0000-000000000304', 'manual', 'station-expired-304', 'manual_review', 'us_law_enforcement', 'verified', now() - interval '1 day');

update public.profiles
set account_class = 'officer', verification_version = 1
where user_id in (
  '00000000-0000-0000-0000-000000000301',
  '00000000-0000-0000-0000-000000000302',
  '00000000-0000-0000-0000-000000000303',
  '00000000-0000-0000-0000-000000000304'
);

insert into public.stations (station_id, name, status)
values ('00000000-0000-0000-0000-000000000311', 'Test Station', 'pending');
insert into public.stations (station_id, name, status)
values ('00000000-0000-0000-0000-000000000312', 'Pending Transfer Station', 'pending');

insert into public.station_memberships (membership_id, station_id, user_id, status)
values
  ('00000000-0000-0000-0000-000000000321', '00000000-0000-0000-0000-000000000311', '00000000-0000-0000-0000-000000000301', 'active'),
  ('00000000-0000-0000-0000-000000000322', '00000000-0000-0000-0000-000000000311', '00000000-0000-0000-0000-000000000302', 'active'),
  ('00000000-0000-0000-0000-000000000323', '00000000-0000-0000-0000-000000000311', '00000000-0000-0000-0000-000000000304', 'active'),
  ('00000000-0000-0000-0000-000000000324', '00000000-0000-0000-0000-000000000312', '00000000-0000-0000-0000-000000000302', 'active');

insert into public.station_membership_roles (membership_id, role)
values
  ('00000000-0000-0000-0000-000000000321', 'station_admin'),
  ('00000000-0000-0000-0000-000000000322', 'viewer'),
  ('00000000-0000-0000-0000-000000000322', 'dispatcher'),
  ('00000000-0000-0000-0000-000000000323', 'viewer');

update public.stations
set status = 'active'
where station_id = '00000000-0000-0000-0000-000000000311';

set local role postgres;
select tests.authenticate_as('00000000-0000-0000-0000-000000000303'::uuid, 'aal2');
select ok(
  not private.is_active_station_member('00000000-0000-0000-0000-000000000303', '00000000-0000-0000-0000-000000000311'),
  'a verified but unassigned user has no station access'
);

select tests.authenticate_as('00000000-0000-0000-0000-000000000302'::uuid, 'aal2');
select ok(private.is_active_station_member('00000000-0000-0000-0000-000000000302', '00000000-0000-0000-0000-000000000311'), 'an assigned verified AAL2 member has station access');
select ok(private.has_station_role('00000000-0000-0000-0000-000000000311', array['viewer']), 'an additive viewer role grants viewer capability');
select ok(private.has_station_role('00000000-0000-0000-0000-000000000311', array['dispatcher']), 'an additive dispatcher role grants dispatcher capability');
select ok(private.has_station_role('00000000-0000-0000-0000-000000000311', array['viewer', 'safety_supervisor']), 'any matching required additive role grants access');
select ok(not private.has_station_role('00000000-0000-0000-0000-000000000311', array['safety_supervisor', 'station_admin']), 'missing roles do not grant access');

update public.station_memberships set status = 'suspended' where membership_id = '00000000-0000-0000-0000-000000000322';
select ok(not private.is_active_station_member('00000000-0000-0000-0000-000000000302', '00000000-0000-0000-0000-000000000311'), 'an inactive membership has no effective access');
update public.station_memberships set status = 'active' where membership_id = '00000000-0000-0000-0000-000000000322';

select tests.authenticate_as('00000000-0000-0000-0000-000000000304'::uuid, 'aal2');
select ok(not private.is_active_station_member('00000000-0000-0000-0000-000000000304', '00000000-0000-0000-0000-000000000311'), 'an expired verification has no effective access');
select tests.authenticate_as('00000000-0000-0000-0000-000000000302'::uuid, 'aal1');
select ok(not private.is_active_station_member('00000000-0000-0000-0000-000000000302', '00000000-0000-0000-0000-000000000311'), 'an AAL1 session has no effective access');
reset role;

insert into public.station_invitations (station_id, token_hash, intended_email, expires_at)
values ('00000000-0000-0000-0000-000000000311', repeat('a', 64), 'invitee@example.test', now() + interval '1 day');
select throws_like(
  $$ insert into public.station_invitations (station_id, token_hash, intended_email, expires_at) values ('00000000-0000-0000-0000-000000000311', repeat('a', 64), 'other@example.test', now() + interval '1 day') $$,
  '%duplicate key%',
  'an invitation hash cannot be reused'
);
update public.station_invitations set used_at = now() where token_hash = repeat('a', 64);
select throws_like(
  $$ update public.station_invitations set used_at = now() + interval '1 second' where token_hash = repeat('a', 64) $$,
  '%invitation has already been used%',
  'an invitation cannot be used twice'
);

insert into public.station_join_requests (station_id, user_id, status)
values ('00000000-0000-0000-0000-000000000311', '00000000-0000-0000-0000-000000000303', 'pending');
select throws_like(
  $$ insert into public.station_join_requests (station_id, user_id, status) values ('00000000-0000-0000-0000-000000000311', '00000000-0000-0000-0000-000000000303', 'pending') $$,
  '%duplicate key%',
  'only one pending join request exists per user and station'
);
update public.station_join_requests set status = 'rejected' where station_id = '00000000-0000-0000-0000-000000000311';
select lives_ok(
  $$ insert into public.station_join_requests (station_id, user_id, status) values ('00000000-0000-0000-0000-000000000311', '00000000-0000-0000-0000-000000000303', 'pending') $$,
  'a new pending join request is allowed after the prior request is resolved'
);

set constraints all immediate;
select throws_ok(
  $$ delete from public.station_membership_roles where membership_id = '00000000-0000-0000-0000-000000000321' and role = 'station_admin' $$,
  '23514',
  null,
  'removing the final active verified station administrator fails'
);
select throws_ok(
  $$ update public.station_memberships set status = 'revoked' where membership_id = '00000000-0000-0000-0000-000000000321' $$,
  '23514',
  null,
  'revoking the final active verified station administrator fails'
);
select throws_ok(
  $$ update public.station_memberships set station_id = '00000000-0000-0000-0000-000000000312' where membership_id = '00000000-0000-0000-0000-000000000321' $$,
  '23514',
  null,
  'moving the final administrator preserves the old active station invariant'
);
select throws_ok(
  $$ update public.station_membership_roles set membership_id = '00000000-0000-0000-0000-000000000324' where membership_id = '00000000-0000-0000-0000-000000000321' and role = 'station_admin' $$,
  '23514',
  null,
  'moving the final administrator role preserves the old active station invariant'
);
select throws_ok(
  $$ update public.officer_verifications set user_id = '00000000-0000-0000-0000-000000000305' where user_id = '00000000-0000-0000-0000-000000000301' $$,
  '23514',
  null,
  'moving the final administrator verification preserves the old active station invariant'
);

set local role authenticated;
select tests.authenticate_as('00000000-0000-0000-0000-000000000302'::uuid, 'aal2');
select throws_like(
  $$ insert into public.station_membership_roles (membership_id, role) values ('00000000-0000-0000-0000-000000000322', 'station_admin') $$,
  '%permission denied%',
  'a client cannot grant itself a station role'
);
select throws_like(
  $$ insert into public.station_memberships (station_id, user_id, status) values ('00000000-0000-0000-0000-000000000311', '00000000-0000-0000-0000-000000000303', 'active') $$,
  '%permission denied%',
  'a client cannot grant station membership directly'
);
reset role;

select ok((select relrowsecurity and relforcerowsecurity from pg_class where oid = 'public.stations'::regclass), 'stations have forced RLS');
select ok((select relrowsecurity and relforcerowsecurity from pg_class where oid = 'public.station_memberships'::regclass), 'memberships have forced RLS');
select ok((select relrowsecurity and relforcerowsecurity from pg_class where oid = 'public.station_membership_roles'::regclass), 'membership roles have forced RLS');
select ok((select prosecdef and proconfig && array['search_path=', 'search_path=""'] from pg_proc where oid = 'private.is_active_station_member(uuid,uuid)'::regprocedure), 'station membership helper is hardened');
select ok((select prosecdef and proconfig && array['search_path=', 'search_path=""'] from pg_proc where oid = 'private.has_station_role(uuid,text[])'::regprocedure), 'station role helper is hardened');

select * from finish();
rollback;
