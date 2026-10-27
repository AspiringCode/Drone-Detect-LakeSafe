-- Keep trusted fictional CAC accounts usable through December 31 Pacific.
-- Ordinary users, revoked verifications, memberships and permissions are unchanged.
begin;

alter table public.cac_judge_access
  drop constraint cac_judge_access_expiry_window;
alter table public.cac_judge_access
  add constraint cac_judge_access_expiry_window check (
    expires_at > created_at
    and expires_at <= timestamptz '2027-01-01 08:00:00+00'
  );

update public.cac_judge_access as access
set expires_at = timestamptz '2027-01-01 08:00:00+00'
from auth.users as account
where account.id = access.user_id
  and account.raw_app_meta_data @>
    '{"fictional_demo":true,"fixture_set":"cac-2026-operators"}'::jsonb;

update public.officer_verifications as verification
set expires_at = timestamptz '2027-01-01 08:00:00+00'
from public.cac_judge_access as access, auth.users as account
where verification.user_id = access.user_id
  and account.id = access.user_id
  and account.raw_app_meta_data @>
    '{"fictional_demo":true,"fixture_set":"cac-2026-operators"}'::jsonb
  and verification.status = 'verified'
  and verification.revoked_at is null
  and verification.expires_at is not null
  and verification.expires_at < timestamptz '2027-01-01 08:00:00+00';

commit;
