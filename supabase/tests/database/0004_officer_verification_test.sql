begin;

select plan(51);

select has_table('public', 'officer_verifications', 'officer verifications table exists');
select has_table('public', 'verification_reviews', 'verification reviews table exists');
select has_table('public', 'verification_evidence', 'verification evidence table exists');
select col_has_check('public', 'officer_verifications', 'provider', 'provider is constrained');
select col_has_check('public', 'officer_verifications', 'method', 'method is constrained');
select col_has_check('public', 'officer_verifications', 'affiliation', 'affiliation is constrained');
select col_has_check('public', 'officer_verifications', 'status', 'status is constrained');
select col_is_unique('public', 'officer_verifications', array['user_id'], 'a user has one verification');
select col_is_unique('public', 'officer_verifications', array['provider_subject'], 'provider subject is unique');

insert into auth.users (id, aud, role, email, encrypted_password, email_confirmed_at, raw_app_meta_data, raw_user_meta_data, created_at, updated_at)
values
  ('00000000-0000-0000-0000-000000000201', 'authenticated', 'authenticated', 'officer@example.test', 'not-used', now(), '{}'::jsonb, '{}'::jsonb, now(), now()),
  ('00000000-0000-0000-0000-000000000202', 'authenticated', 'authenticated', 'reviewer@example.test', 'not-used', now(), '{}'::jsonb, '{}'::jsonb, now(), now()),
  ('00000000-0000-0000-0000-000000000203', 'authenticated', 'authenticated', 'self-reviewer@example.test', 'not-used', now(), '{}'::jsonb, '{}'::jsonb, now(), now()),
  ('00000000-0000-0000-0000-000000000204', 'authenticated', 'authenticated', 'expired@example.test', 'not-used', now(), '{}'::jsonb, '{}'::jsonb, now(), now()),
  ('00000000-0000-0000-0000-000000000205', 'authenticated', 'authenticated', 'other@example.test', 'not-used', now(), '{}'::jsonb, '{}'::jsonb, now(), now());

insert into public.platform_staff_roles (user_id, role, active)
values
  ('00000000-0000-0000-0000-000000000202', 'verification_reviewer', true),
  ('00000000-0000-0000-0000-000000000203', 'verification_reviewer', true);

set local role authenticated;
select tests.authenticate_as('00000000-0000-0000-0000-000000000201'::uuid, 'aal2');

select lives_ok(
  $$ select public.submit_officer_verification('id_me', 'idme-officer-201', 'oidc', 'us_law_enforcement') $$,
  'an officer can submit a verification'
);

select is(
  (select status from public.officer_verifications where user_id = '00000000-0000-0000-0000-000000000201'),
  'pending',
  'submission starts pending'
);

select throws_like(
  $$ select public.review_officer_verification((select verification_id from public.officer_verifications where user_id = '00000000-0000-0000-0000-000000000201'), 'verified') $$,
  '%not an active verification reviewer%',
  'a subject cannot approve their own verification'
);

select tests.authenticate_as('00000000-0000-0000-0000-000000000202'::uuid, 'aal2');

select lives_ok(
  $$ select public.review_officer_verification((select verification_id from public.officer_verifications where user_id = '00000000-0000-0000-0000-000000000201'), 'verified') $$,
  'an active reviewer can verify a pending officer'
);

reset role;

insert into public.officer_verifications (user_id, provider, provider_subject, method, affiliation)
values ('00000000-0000-0000-0000-000000000203', 'manual', 'manual-officer-203', 'manual_review', 'us_law_enforcement');
select lives_ok($$ select private.transition_officer_verification((select verification_id from public.officer_verifications where user_id = '00000000-0000-0000-0000-000000000203'), 'pending') $$, 'not started can transition to pending through the helper');
select lives_ok(
  $$ do $check$
  declare
    source_status text;
    target_status text;
    target_verification_id uuid;
    target_user_id uuid;
  begin
    foreach source_status in array array['not_started', 'pending', 'verified', 'rejected', 'expired', 'revoked'] loop
      foreach target_status in array array['not_started', 'pending', 'verified', 'rejected', 'expired', 'revoked'] loop
        if not (
          (source_status = 'not_started' and target_status = 'pending')
          or (source_status = 'pending' and target_status in ('verified', 'rejected'))
          or (source_status = 'verified' and target_status in ('expired', 'revoked'))
          or (source_status in ('rejected', 'expired') and target_status = 'pending')
        ) then
          target_user_id := gen_random_uuid();
          insert into auth.users (id, aud, role, email, encrypted_password, email_confirmed_at, raw_app_meta_data, raw_user_meta_data, created_at, updated_at)
          values (target_user_id, 'authenticated', 'authenticated', target_user_id::text || '@example.test', 'not-used', now(), '{}'::jsonb, '{}'::jsonb, now(), now());
          insert into public.officer_verifications (user_id, provider, provider_subject, method, affiliation, status)
          values (target_user_id, 'manual', gen_random_uuid()::text, 'manual_review', 'us_law_enforcement', source_status)
          returning verification_id into target_verification_id;
          begin
            perform private.transition_officer_verification(target_verification_id, target_status);
            raise exception 'disallowed transition % -> % was accepted', source_status, target_status;
          exception when sqlstate '22023' then
            null;
          end;
        end if;
      end loop;
    end loop;
  end;
  $check$ $$,
  'every disallowed verification state edge is rejected by the helper'
);

select is(
  (select account_class from public.profiles where user_id = '00000000-0000-0000-0000-000000000201'),
  'officer',
  'verification promotes the profile while current'
);
select is(
  (select verification_version from public.profiles where user_id = '00000000-0000-0000-0000-000000000201'),
  1,
  'verification transition increments profile version'
);
select ok(
  private.officer_verification_is_current((select verification_id from public.officer_verifications where user_id = '00000000-0000-0000-0000-000000000201')),
  'a verified, unexpired, unrevoked verification is current'
);
select throws_like($$ select private.transition_officer_verification((select verification_id from public.officer_verifications where user_id = '00000000-0000-0000-0000-000000000201'), 'pending') $$, '%invalid verification transition%', 'verified cannot return directly to pending');

select lives_ok(
  $$ select private.transition_officer_verification((select verification_id from public.officer_verifications where user_id = '00000000-0000-0000-0000-000000000201'), 'expired') $$,
  'verified can expire'
);
select ok(
  not private.officer_verification_is_current((select verification_id from public.officer_verifications where user_id = '00000000-0000-0000-0000-000000000201')),
  'expired verification is not current'
);
select is((select account_class from public.profiles where user_id = '00000000-0000-0000-0000-000000000201'), 'civilian', 'expiry demotes the profile');
select throws_like($$ select private.transition_officer_verification((select verification_id from public.officer_verifications where user_id = '00000000-0000-0000-0000-000000000201'), 'rejected') $$, '%invalid verification transition%', 'expired cannot reject');
select lives_ok($$ select private.transition_officer_verification((select verification_id from public.officer_verifications where user_id = '00000000-0000-0000-0000-000000000201'), 'pending') $$, 'expired can return to pending');
select throws_like($$ select private.transition_officer_verification((select verification_id from public.officer_verifications where user_id = '00000000-0000-0000-0000-000000000201'), 'expired') $$, '%invalid verification transition%', 'pending cannot expire directly');
select lives_ok($$ select private.transition_officer_verification((select verification_id from public.officer_verifications where user_id = '00000000-0000-0000-0000-000000000201'), 'rejected') $$, 'pending can be rejected');
select throws_like($$ select private.transition_officer_verification((select verification_id from public.officer_verifications where user_id = '00000000-0000-0000-0000-000000000201'), 'verified') $$, '%invalid verification transition%', 'rejected cannot directly verify');
select lives_ok($$ select private.transition_officer_verification((select verification_id from public.officer_verifications where user_id = '00000000-0000-0000-0000-000000000201'), 'pending') $$, 'rejected can return to pending');
select lives_ok($$ select private.transition_officer_verification((select verification_id from public.officer_verifications where user_id = '00000000-0000-0000-0000-000000000201'), 'verified') $$, 'pending can verify');
select lives_ok($$ select private.transition_officer_verification((select verification_id from public.officer_verifications where user_id = '00000000-0000-0000-0000-000000000201'), 'revoked') $$, 'verified can revoke');
select is((select account_class from public.profiles where user_id = '00000000-0000-0000-0000-000000000201'), 'civilian', 'revocation demotes the profile');
select ok(not private.officer_verification_is_current((select verification_id from public.officer_verifications where user_id = '00000000-0000-0000-0000-000000000201')), 'revoked verification is not current');
select throws_like($$ select private.transition_officer_verification((select verification_id from public.officer_verifications where user_id = '00000000-0000-0000-0000-000000000201'), 'verified') $$, '%invalid verification transition%', 'revoked cannot directly verify');
select throws_like($$ select private.transition_officer_verification((select verification_id from public.officer_verifications where user_id = '00000000-0000-0000-0000-000000000201'), 'pending') $$, '%invalid verification transition%', 'revoked cannot return to pending');

insert into public.officer_verifications (user_id, provider, provider_subject, method, affiliation, status, expires_at)
values ('00000000-0000-0000-0000-000000000204', 'manual', 'manual-officer-204', 'manual_review', 'us_law_enforcement', 'verified', now() - interval '1 second');
update public.profiles set account_class = 'officer', verification_version = 5 where user_id = '00000000-0000-0000-0000-000000000204';
select ok(not private.officer_verification_is_current((select verification_id from public.officer_verifications where user_id = '00000000-0000-0000-0000-000000000204')), 'evaluating a due verification returns false');
select is((select status from public.officer_verifications where user_id = '00000000-0000-0000-0000-000000000204'), 'expired', 'evaluation transitions a due verification to expired');
select is((select account_class from public.profiles where user_id = '00000000-0000-0000-0000-000000000204'), 'civilian', 'time-only expiry evaluation demotes the profile');
select is((select verification_version from public.profiles where user_id = '00000000-0000-0000-0000-000000000204'), 6, 'time-only expiry evaluation increments the profile version');

set local role authenticated;
select tests.authenticate_as('00000000-0000-0000-0000-000000000203'::uuid, 'aal2');
select throws_like(
  $$ select public.review_officer_verification((select verification_id from public.officer_verifications where user_id = '00000000-0000-0000-0000-000000000203'), 'verified') $$,
  '%reviewers cannot approve their own verification%',
  'an active reviewer cannot approve their own verification through the review RPC'
);
select throws_like(
  $$ insert into public.verification_reviews (verification_id, reviewer_user_id, decision) select verification_id, '00000000-0000-0000-0000-000000000203'::uuid, 'verified' from public.officer_verifications where user_id = '00000000-0000-0000-0000-000000000203' $$,
  '%row-level security%',
  'a reviewer cannot directly review their own pending verification'
);
select tests.authenticate_as('00000000-0000-0000-0000-000000000205'::uuid, 'aal2');
select results_eq($$ select verification_id from public.officer_verifications $$, $$ select null::uuid where false $$, 'a different user cannot read another verification');
select throws_like($$ update public.officer_verifications set status = 'verified' $$, '%permission denied%', 'clients cannot update verification state directly');
select throws_like($$ insert into public.verification_evidence (verification_id, storage_path, evidence_type, content_hash) values ('00000000-0000-0000-0000-000000000201', 'private/path', 'badge', 'hash') $$, '%permission denied%', 'clients cannot append evidence directly');
reset role;

select lives_ok($$ insert into public.verification_evidence (verification_id, storage_path, evidence_type, content_hash) select verification_id, 'private/path', 'badge', 'hash' from public.officer_verifications where user_id = '00000000-0000-0000-0000-000000000201' $$, 'evidence contains metadata only');
select throws_like($$ update public.verification_evidence set deleted_at = now() $$, '%append-only%', 'evidence is append-only');
select throws_like($$ delete from public.verification_reviews $$, '%append-only%', 'reviews are append-only');

select ok((select relrowsecurity and relforcerowsecurity from pg_class where oid = 'public.officer_verifications'::regclass), 'verifications have forced RLS');
select ok((select relrowsecurity and relforcerowsecurity from pg_class where oid = 'public.verification_reviews'::regclass), 'reviews have forced RLS');
select ok((select relrowsecurity and relforcerowsecurity from pg_class where oid = 'public.verification_evidence'::regclass), 'evidence has forced RLS');
select ok((select prosecdef and proconfig @> array['search_path='] from pg_proc where oid = 'private.transition_officer_verification(uuid,text)'::regprocedure), 'transition helper is hardened');
select ok((select prosecdef and proconfig @> array['search_path='] from pg_proc where oid = 'private.officer_verification_is_current(uuid)'::regprocedure), 'current verification helper is hardened');

select * from finish();
rollback;
