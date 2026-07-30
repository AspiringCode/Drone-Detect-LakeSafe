begin;
select plan(15);

select row_security_is_enabled('public', 'operational_alerts', 'operational alerts use RLS');
select row_security_is_enabled('public', 'drone_telemetry', 'telemetry uses RLS');
select row_security_is_enabled('public', 'command_outbox', 'commands use RLS');
select row_security_is_enabled('public', 'verification_evidence', 'verification evidence uses RLS');
select row_security_is_enabled('public', 'audit_events', 'audit events use RLS');
select table_privs_are('anon', 'public', 'operational_alerts', array[]::text[], 'anon cannot read operational alerts');
select table_privs_are('anon', 'public', 'drone_telemetry', array[]::text[], 'anon cannot read telemetry');
select table_privs_are('anon', 'public', 'command_outbox', array[]::text[], 'anon cannot read commands');
select table_privs_are('authenticated', 'public', 'operational_alerts', array['SELECT']::text[], 'operations reads are policy bound');
select table_privs_are('authenticated', 'public', 'public_alerts', array['SELECT']::text[], 'authenticated receives only public projection read');
select table_privs_are('anon', 'public', 'public_alerts', array['SELECT']::text[], 'anon receives only public projection read');
select function_privs_are('private', 'jwt_aal', array['EXECUTE']::text[], 'jwt helper is explicitly executable');
select function_privs_are('private', 'is_active_station_member', array['EXECUTE']::text[], 'membership helper is explicitly executable');
select results_eq(
  $$select schemaname || '.' || tablename from pg_publication_tables where pubname = 'supabase_realtime' order by 1$$,
  $$values ('public.public_alerts'::text), ('public.public_patrol_presence'::text)$$,
  'Realtime contains only sanitized public projections'
);
select is_empty(
  $$select 1 from pg_publication_tables where pubname = 'supabase_realtime' and tablename in ('operational_alerts', 'drone_telemetry', 'command_outbox')$$,
  'operational tables are absent from public Realtime'
);

select * from finish();
rollback;
