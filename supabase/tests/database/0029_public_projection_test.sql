begin;
select plan(16);

select has_table('public', 'operational_alerts', 'operational alerts are private');
select has_table('public', 'legacy_alerts', 'legacy alerts are retained only for migration audit');
select has_table('public', 'public_lakes', 'public lakes projection exists');
select has_table('public', 'public_alerts', 'public alerts projection exists');
select has_table('public', 'public_patrol_presence', 'public patrol projection exists');
select has_column('public', 'operational_alerts', 'precise_location', 'private alert keeps precise location');
select hasnt_column('public', 'public_alerts', 'precise_location', 'public alert omits precise location');
select hasnt_column('public', 'public_alerts', 'evidence_ref', 'public alert omits evidence');
select hasnt_column('public', 'public_alerts', 'response_tactics', 'public alert omits tactics');
select ok((select relrowsecurity from pg_class where oid = 'public.operational_alerts'::regclass), 'operational alerts RLS enabled');
select ok((select relrowsecurity from pg_class where oid = 'public.legacy_alerts'::regclass), 'legacy alerts RLS enabled');
select ok((select relrowsecurity from pg_class where oid = 'public.public_alerts'::regclass), 'public alert RLS enabled');
select table_privs_are('public', 'public_alerts', 'anon', array['SELECT']::text[], 'anon reads only public alert projection');
select table_privs_are('public', 'operational_alerts', 'anon', array[]::text[], 'anon cannot read operational alerts');
select table_privs_are('public', 'legacy_alerts', 'anon', array[]::text[], 'anon cannot read legacy alerts');
select ok(exists (select 1 from pg_policies where schemaname = 'public' and tablename = 'public_alerts' and policyname = 'public_alerts_select_everyone'), 'public alert select policy exists');

select * from finish();
rollback;
