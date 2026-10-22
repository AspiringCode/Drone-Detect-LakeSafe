begin;
select plan(12);

select has_table('public', 'privileged_rate_limit_buckets', 'durable privileged limiter exists');
select has_pk('public', 'privileged_rate_limit_buckets', 'bucket key is atomic per scope and subject');
select ok((select relrowsecurity from pg_class where oid = 'public.privileged_rate_limit_buckets'::regclass), 'bucket RLS is enabled');
select throws_ok(
  'set local role authenticated; select public.claim_rate_limit(''test'', ''station:test:user:test'', 1, 60)',
  '42501', null, 'authenticated callers cannot execute rate limit claims'
);
select table_privs_are('public', 'privileged_rate_limit_buckets', 'anon', array[]::text[], 'anon cannot access durable buckets');
select table_privs_are('public', 'privileged_rate_limit_buckets', 'authenticated', array[]::text[], 'authenticated cannot access durable buckets');
select ok(position('pg_advisory_xact_lock' in pg_get_functiondef('public.claim_rate_limit(text,text,integer,integer)'::regprocedure)) > 0,
  'rate-limit claims serialize first bucket creation as well as updates');

select lives_ok(
  $$select public.claim_rate_limit('pgtap:rate-limit', 'subject:first', 1, 60)$$,
  'first claim creates a bucket without invalid advisory-lock text'
);
select is(public.claim_rate_limit('pgtap:rate-limit', 'subject:first', 1, 60)->>'allowed', 'false',
  'second claim in the same window is denied');
select is((select request_count from public.privileged_rate_limit_buckets where scope = 'pgtap:rate-limit' and subject = 'subject:first'), 1,
  'denied claims do not increase the request count');
select is(public.claim_rate_limit('pgtap:rate-limit', 'subject:second', 1, 60)->>'allowed', 'true',
  'another subject has an independent bucket');
update public.privileged_rate_limit_buckets set window_started_at = clock_timestamp() - interval '2 minutes'
where scope = 'pgtap:rate-limit' and subject = 'subject:first';
select is(public.claim_rate_limit('pgtap:rate-limit', 'subject:first', 1, 60)->>'allowed', 'true',
  'expired window allows a new claim');

select * from finish();
rollback;
