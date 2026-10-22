begin;
select plan(14);

select is(pg_get_function_result('public.claim_queued_risk_refreshes(integer)'::regprocedure),
  'TABLE(lake_id text, claim_token uuid)', 'queued claims return their lease token');
select is(pg_get_function_result('public.claim_due_risk_source_refreshes(integer)'::regprocedure),
  'TABLE(lake_id text, claim_token uuid)', 'source claims return their lease token');

select ok(has_function_privilege('service_role', 'public.claim_queued_risk_refreshes(integer)', 'EXECUTE'), 'server can claim queued refreshes');
select ok(not has_function_privilege('anon', 'public.claim_queued_risk_refreshes(integer)', 'EXECUTE'), 'anonymous clients cannot claim queued refreshes');
select ok(not has_function_privilege('authenticated', 'public.claim_queued_risk_refreshes(integer)', 'EXECUTE'), 'browser clients cannot claim queued refreshes');
select ok(has_function_privilege('service_role', 'public.claim_due_risk_source_refreshes(integer)', 'EXECUTE'), 'server can claim source refreshes');
select ok(not has_function_privilege('anon', 'public.claim_due_risk_source_refreshes(integer)', 'EXECUTE'), 'anonymous clients cannot claim source refreshes');
select ok(not has_function_privilege('authenticated', 'public.claim_due_risk_source_refreshes(integer)', 'EXECUTE'), 'browser clients cannot claim source refreshes');
select ok(has_function_privilege('service_role', 'public.expire_real_command_delivery(uuid,text,integer)', 'EXECUTE'), 'server can expire real commands');
select ok(not has_function_privilege('anon', 'public.expire_real_command_delivery(uuid,text,integer)', 'EXECUTE'), 'anonymous clients cannot expire real commands');
select ok(not has_function_privilege('authenticated', 'public.expire_real_command_delivery(uuid,text,integer)', 'EXECUTE'), 'browser clients cannot expire real commands');

select lives_ok('select * from public.claim_queued_risk_refreshes(1)', 'queued claim function executes');
select lives_ok('select * from public.claim_due_risk_source_refreshes(1)', 'source claim function executes');
select lives_ok($test$select * from public.expire_real_command_delivery('00000000-0000-0000-0000-000000000000'::uuid, 'migration-contract-test', 3)$test$,
  'SQL command expiry function executes');

select * from finish();
rollback;
