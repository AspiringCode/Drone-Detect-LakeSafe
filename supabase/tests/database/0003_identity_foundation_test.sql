begin;

select plan(21);

select has_table('public', 'profiles', 'profiles table exists');
select has_table('public', 'platform_staff_roles', 'platform staff roles table exists');
select col_is_pk('public', 'profiles', 'user_id', 'profiles user_id is the primary key');
select fk_ok('public', 'profiles', 'user_id', 'auth', 'users', 'id', 'profiles user_id references auth.users');
select col_default_is('public', 'profiles', 'account_class', 'civilian', 'profiles default to civilian');
select ok(exists (select 1 from pg_constraint c join pg_attribute a on a.attrelid = c.conrelid and a.attnum = any(c.conkey) where c.conrelid = 'public.profiles'::regclass and c.contype = 'c' and a.attname = 'account_class'), 'profiles account class is constrained');
select ok(exists (select 1 from pg_constraint c join pg_attribute a on a.attrelid = c.conrelid and a.attnum = any(c.conkey) where c.conrelid = 'public.profiles'::regclass and c.contype = 'c' and a.attname = 'verification_version'), 'profiles verification version is constrained');
select has_function('private', 'handle_new_user', array[]::text[], 'new user handler exists');
select has_function('private', 'jwt_aal', array[]::text[], 'jwt aal helper exists');
select has_function('private', 'is_platform_staff', array['text'], 'platform staff helper exists');
select ok(exists (select 1 from pg_policies where schemaname = 'public' and tablename = 'profiles' and policyname = 'profiles_select_own'), 'profiles has own-row select policy');
select ok(exists (select 1 from pg_policies where schemaname = 'public' and tablename = 'profiles' and policyname = 'profiles_update_own_display_name'), 'profiles has own-row update policy');
select ok(
  (select relrowsecurity and relforcerowsecurity from pg_class where oid = 'public.profiles'::regclass),
  'profiles has forced row level security'
);
select ok(
  (
    select prosecdef and proconfig && array['search_path=', 'search_path=""']
    from pg_proc
    where oid = 'private.handle_new_user()'::regprocedure
  ),
  'new user handler is security definer with an empty search path'
);

insert into auth.users (
  id, aud, role, email, encrypted_password, email_confirmed_at,
  raw_app_meta_data, raw_user_meta_data, created_at, updated_at
) values
  ('00000000-0000-0000-0000-000000000101', 'authenticated', 'authenticated', 'identity-one@example.test', 'not-used', now(), '{}'::jsonb, '{"display_name":"Identity One"}'::jsonb, now(), now()),
  ('00000000-0000-0000-0000-000000000102', 'authenticated', 'authenticated', 'identity-two@example.test', 'not-used', now(), '{}'::jsonb, '{"display_name":"Identity Two"}'::jsonb, now(), now());

select is(
  (select account_class from public.profiles where user_id = '00000000-0000-0000-0000-000000000101'),
  'civilian',
  'new user handler creates a civilian profile'
);

select is(
  (select private.jwt_aal()),
  '',
  'jwt aal is empty when no request claims are set'
);

set local role authenticated;
select tests.authenticate_as('00000000-0000-0000-0000-000000000101'::uuid, 'aal2');

select results_eq(
  $$ select user_id from public.profiles order by user_id $$,
  $$ values ('00000000-0000-0000-0000-000000000101'::uuid) $$,
  'an authenticated user sees only their own profile'
);

select lives_ok(
  $$ update public.profiles set display_name = 'Renamed Identity One' where user_id = '00000000-0000-0000-0000-000000000101' $$,
  'an authenticated user can update their display name'
);

select throws_like(
  $$ update public.profiles set account_class = 'officer' where user_id = '00000000-0000-0000-0000-000000000101' $$,
  '%permission denied%',
  'an authenticated user cannot promote their account class'
);

select throws_like(
  $$ update public.profiles set verification_version = 1 where user_id = '00000000-0000-0000-0000-000000000101' $$,
  '%permission denied%',
  'an authenticated user cannot update verification version'
);

select throws_like(
  $$ insert into public.platform_staff_roles (user_id, role) values ('00000000-0000-0000-0000-000000000101', 'system_admin') $$,
  '%permission denied%',
  'an authenticated user cannot grant themselves a platform staff role'
);

select * from finish();
rollback;
