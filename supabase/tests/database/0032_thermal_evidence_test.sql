begin;
select plan(4);

select results_eq(
  $$ select public from storage.buckets where id = 'thermal-clips' $$,
  $$ values (false) $$,
  'thermal clips bucket is private'
);
select table_privs_are('anon', 'storage', 'objects', array[]::text[], 'anon cannot read thermal objects directly');
select table_privs_are('authenticated', 'storage', 'objects', array[]::text[], 'authenticated cannot read thermal objects directly');
select has_table('public', 'operational_alerts', 'evidence authorization resolves private operational alerts');

select * from finish();
rollback;
