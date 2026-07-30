begin;
select plan(13);

select has_table('public', 'operational_alerts', 'operational alerts are private');
select has_table('public', 'public_lakes', 'public lakes projection exists');
select has_table('public', 'public_alerts', 'public alerts projection exists');
select has_table('public', 'public_patrol_presence', 'public patrol projection exists');
select has_column('public', 'operational_alerts', 'precise_location', 'private alert keeps precise location');
select hasnt_column('public', 'public_alerts', 'precise_location', 'public alert omits precise location');
select hasnt_column('public', 'public_alerts', 'evidence_ref', 'public alert omits evidence');
select hasnt_column('public', 'public_alerts', 'response_tactics', 'public alert omits tactics');
select row_security_is_enabled('public', 'operational_alerts', 'operational alerts RLS enabled');
select row_security_is_enabled('public', 'public_alerts', 'public alert RLS enabled');
select table_privs_are('anon', 'public', 'public_alerts', array['SELECT']::text[], 'anon reads only public alert projection');
select table_privs_are('anon', 'public', 'operational_alerts', array[]::text[], 'anon cannot read operational alerts');
select policy_exists('public', 'public_alerts', 'public_alerts_select_everyone', 'public alert select policy exists');

select * from finish();
rollback;
