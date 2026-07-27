create extension if not exists pgtap;

create schema if not exists tests;
grant usage on schema tests to authenticated;

create or replace function tests.authenticate_as(
  target_user_id uuid,
  target_aal text default 'aal1'
)
returns void
language plpgsql
as $$
declare
  target_session_id uuid := '00000000-0000-0000-0000-000000000001';
begin
  perform set_config('request.jwt.claim.sub', target_user_id::text, true);
  perform set_config('request.jwt.claim.role', 'authenticated', true);
  perform set_config('request.jwt.claim.aal', target_aal, true);
  perform set_config('request.jwt.claim.session_id', target_session_id::text, true);
  perform set_config(
    'request.jwt.claims',
    jsonb_build_object(
      'sub', target_user_id,
      'role', 'authenticated',
      'aal', target_aal,
      'session_id', target_session_id
    )::text,
    true
  );
end;
$$;

grant execute on function tests.authenticate_as(uuid, text) to authenticated;

select plan(1);
select pass('database authentication helper is installed');
select * from finish();
