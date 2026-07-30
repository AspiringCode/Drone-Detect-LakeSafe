begin;
select plan(6);

select has_table('public', 'privileged_rate_limit_buckets', 'durable privileged limiter exists');
select has_pk('public', 'privileged_rate_limit_buckets', 'bucket key is atomic per scope and subject');
select row_security_is_enabled('public', 'privileged_rate_limit_buckets', 'bucket RLS is enabled');
select throws_ok(
  'set local role authenticated; select public.claim_rate_limit(''test'', ''station:test:user:test'', 1, 60)',
  '42501', null, 'authenticated callers cannot execute rate limit claims'
);
select table_privs_are('anon', 'public', 'privileged_rate_limit_buckets', array[]::text[], 'anon cannot access durable buckets');
select table_privs_are('authenticated', 'public', 'privileged_rate_limit_buckets', array[]::text[], 'authenticated cannot access durable buckets');

select * from finish();
rollback;
