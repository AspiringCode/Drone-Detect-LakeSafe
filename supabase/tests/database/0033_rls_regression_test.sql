begin;
select plan(15);

select ok((select relrowsecurity from pg_class where oid = 'public.operational_alerts'::regclass), 'operational alerts use RLS');
select ok((select relrowsecurity from pg_class where oid = 'public.drone_telemetry'::regclass), 'telemetry uses RLS');
select ok((select relrowsecurity from pg_class where oid = 'public.command_outbox'::regclass), 'commands use RLS');
select ok((select relrowsecurity from pg_class where oid = 'public.verification_evidence'::regclass), 'verification evidence uses RLS');
select ok((select relrowsecurity from pg_class where oid = 'public.audit_events'::regclass), 'audit events use RLS');
select table_privs_are('public', 'operational_alerts', 'anon', array[]::text[], 'anon cannot read operational alerts');
select table_privs_are('public', 'drone_telemetry', 'anon', array[]::text[], 'anon cannot read telemetry');
select table_privs_are('public', 'command_outbox', 'anon', array[]::text[], 'anon cannot read commands');
select table_privs_are('public', 'operational_alerts', 'authenticated', array['SELECT']::text[], 'operations reads are policy bound');
select table_privs_are('public', 'public_alerts', 'authenticated', array['SELECT']::text[], 'authenticated receives only public projection read');
select table_privs_are('public', 'public_alerts', 'anon', array['SELECT']::text[], 'anon receives only public projection read');
select function_privs_are('private', 'jwt_aal', array[]::text[], 'authenticated', array['EXECUTE']::text[], 'jwt helper is explicitly executable');
select function_privs_are('private', 'is_active_station_member', array['uuid', 'uuid']::text[], 'authenticated', array['EXECUTE']::text[], 'membership helper is explicitly executable');
select results_eq(
  $$select (schemaname::text || '.' || tablename::text) collate "C" from pg_publication_tables where pubname = 'supabase_realtime' order by 1$$,
  $$values ('public.public_alerts'::text collate "C"), ('public.public_patrol_presence'::text collate "C")$$,
  'Realtime contains only sanitized public projections'
);
select is_empty(
  $$select 1 from pg_publication_tables where pubname = 'supabase_realtime' and tablename in ('operational_alerts', 'drone_telemetry', 'command_outbox')$$,
  'operational tables are absent from public Realtime'
);

select * from finish();
rollback;
