begin;
select plan(8);

select has_table('public', 'audit_events', 'audit event table exists');
select table_privs_are('anon', 'public', 'audit_events', array[]::text[], 'anon has no audit table privileges');
select table_privs_are('authenticated', 'public', 'audit_events', array['SELECT']::text[], 'authenticated reads are constrained by RLS');
select policies_are('public', 'audit_events', array['audit_events_select_scoped'], 'audit reads use a single scoped policy');
select has_trigger('public', 'audit_events', 'reject_audit_update_delete', 'audit update/delete rejection trigger exists');
select function_privs_are('private', 'reject_audit_mutation', array[]::text[], 'append-only trigger function is not client executable');
select has_check('public', 'audit_events', 'audit_events_exactly_one_actor', 'audit event requires exactly one actor');
select col_not_null('public', 'audit_events', 'request_id', 'audit event request IDs are mandatory');

select * from finish();
rollback;
