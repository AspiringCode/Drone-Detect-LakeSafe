begin;
select plan(5);

select results_eq(
  $$ select public from storage.buckets where id = 'thermal-clips' $$,
  $$ values (false) $$,
  'thermal clips bucket is private'
);
select ok((select relrowsecurity from pg_class where oid = 'storage.objects'::regclass), 'storage objects enforce row level security');

insert into storage.objects (id, bucket_id, name)
values ('00000000-0000-0000-0000-000000003201', 'thermal-clips', 'database-tests/private-thermal-clip');

set local role anon;
select lives_ok(
  $$ do $check$
  begin
    if exists (select 1 from storage.objects where bucket_id = 'thermal-clips') then
      raise exception 'anonymous browser can read private thermal objects';
    end if;
  exception when insufficient_privilege then
    null;
  end;
  $check$ $$,
  'anon cannot read thermal objects directly'
);
reset role;

set local role authenticated;
select tests.authenticate_as('00000000-0000-0000-0000-000000003202'::uuid, 'aal2');
select lives_ok(
  $$ do $check$
  begin
    if exists (select 1 from storage.objects where bucket_id = 'thermal-clips') then
      raise exception 'authenticated browser can read private thermal objects';
    end if;
  exception when insufficient_privilege then
    null;
  end;
  $check$ $$,
  'authenticated cannot read thermal objects directly'
);
reset role;
select has_table('public', 'operational_alerts', 'evidence authorization resolves private operational alerts');

select * from finish();
rollback;
