create table public.officer_verifications (
  verification_id uuid primary key default gen_random_uuid(),
  user_id uuid not null unique references auth.users(id) on delete cascade,
  provider text not null check (provider in ('id_me', 'manual')),
  provider_subject text not null unique,
  method text not null check (method in ('oidc', 'manual_review')),
  affiliation text not null check (affiliation = 'us_law_enforcement'),
  status text not null default 'not_started' check (status in ('not_started', 'pending', 'verified', 'rejected', 'expired', 'revoked')),
  verified_at timestamptz,
  expires_at timestamptz,
  revoked_at timestamptz,
  version bigint not null default 0 check (version >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check ((provider = 'id_me' and method = 'oidc') or (provider = 'manual' and method = 'manual_review'))
);

create table public.verification_reviews (
  review_id uuid primary key default gen_random_uuid(),
  verification_id uuid not null references public.officer_verifications(verification_id) on delete cascade,
  reviewer_user_id uuid not null references auth.users(id),
  decision text not null check (decision in ('verified', 'rejected')),
  note text,
  created_at timestamptz not null default now()
);

create table public.verification_evidence (
  evidence_id uuid primary key default gen_random_uuid(),
  verification_id uuid not null references public.officer_verifications(verification_id) on delete cascade,
  storage_path text not null,
  evidence_type text not null,
  content_hash text not null,
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  unique (verification_id, storage_path)
);

create or replace function private.prevent_verification_history_mutation()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  raise exception '% is append-only', tg_table_name using errcode = '55000';
end;
$$;

create trigger verification_reviews_append_only
  before update or delete on public.verification_reviews
  for each row execute procedure private.prevent_verification_history_mutation();

create trigger verification_evidence_append_only
  before update or delete on public.verification_evidence
  for each row execute procedure private.prevent_verification_history_mutation();

create or replace function private.officer_verification_is_current(target_verification_id uuid)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  current_verification public.officer_verifications%rowtype;
begin
  select * into current_verification
  from public.officer_verifications
  where verification_id = target_verification_id
  for update;

  if not found then
    return false;
  end if;

  if current_verification.status = 'verified'
    and current_verification.expires_at is not null
    and current_verification.expires_at <= now() then
    update public.officer_verifications
    set status = 'expired',
        version = version + 1,
        updated_at = now()
    where verification_id = target_verification_id;

    update public.profiles
    set account_class = 'civilian',
        verification_version = verification_version + 1,
        updated_at = now()
    where user_id = current_verification.user_id;

    return false;
  end if;

  return current_verification.status = 'verified'
    and (current_verification.expires_at is null or current_verification.expires_at > now())
    and current_verification.revoked_at is null;
end;
$$;

create or replace function private.transition_officer_verification(
  target_verification_id uuid,
  target_status text
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  current_verification public.officer_verifications%rowtype;
  becomes_current boolean;
begin
  select * into current_verification
  from public.officer_verifications
  where verification_id = target_verification_id
  for update;

  if not found then
    raise exception 'officer verification not found' using errcode = 'P0002';
  end if;

  if not (
    (current_verification.status = 'not_started' and target_status = 'pending')
    or (current_verification.status = 'pending' and target_status in ('verified', 'rejected'))
    or (current_verification.status = 'verified' and target_status in ('expired', 'revoked'))
    or (current_verification.status in ('rejected', 'expired') and target_status = 'pending')
  ) then
    raise exception 'invalid verification transition from % to %', current_verification.status, target_status
      using errcode = '22023';
  end if;

  update public.officer_verifications
  set status = target_status,
      verified_at = case when target_status = 'verified' then now() else verified_at end,
      expires_at = case when target_status = 'verified' then null when target_status = 'expired' then coalesce(expires_at, now()) else expires_at end,
      revoked_at = case when target_status = 'revoked' then now() else revoked_at end,
      version = version + 1,
      updated_at = now()
  where verification_id = target_verification_id;

  select private.officer_verification_is_current(target_verification_id) into becomes_current;

  update public.profiles
  set account_class = case when becomes_current then 'officer' else 'civilian' end,
      verification_version = verification_version + 1,
      updated_at = now()
  where user_id = current_verification.user_id;
end;
$$;

create or replace function public.submit_officer_verification(
  requested_provider text,
  requested_provider_subject text,
  requested_method text,
  requested_affiliation text
)
returns uuid
language plpgsql
security definer
set search_path = ''
as $$
declare
  new_verification_id uuid;
begin
  if auth.uid() is null then
    raise exception 'authentication required' using errcode = '42501';
  end if;

  insert into public.officer_verifications (user_id, provider, provider_subject, method, affiliation)
  values (auth.uid(), requested_provider, requested_provider_subject, requested_method, requested_affiliation)
  returning verification_id into new_verification_id;

  perform private.transition_officer_verification(new_verification_id, 'pending');
  return new_verification_id;
end;
$$;

create or replace function public.review_officer_verification(
  target_verification_id uuid,
  requested_decision text,
  review_note text default null
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
declare
  verification_subject uuid;
begin
  if auth.uid() is null or not private.is_platform_staff('verification_reviewer') then
    raise exception 'not an active verification reviewer' using errcode = '42501';
  end if;

  select user_id into verification_subject
  from public.officer_verifications
  where verification_id = target_verification_id;

  if not found then
    raise exception 'officer verification not found' using errcode = 'P0002';
  end if;

  if verification_subject = auth.uid() then
    raise exception 'reviewers cannot approve their own verification' using errcode = '42501';
  end if;

  if requested_decision not in ('verified', 'rejected') then
    raise exception 'review decision must be verified or rejected' using errcode = '22023';
  end if;

  perform private.transition_officer_verification(target_verification_id, requested_decision);

  insert into public.verification_reviews (verification_id, reviewer_user_id, decision, note)
  values (target_verification_id, auth.uid(), requested_decision, review_note);
end;
$$;

alter table public.officer_verifications enable row level security;
alter table public.officer_verifications force row level security;
alter table public.verification_reviews enable row level security;
alter table public.verification_reviews force row level security;
alter table public.verification_evidence enable row level security;
alter table public.verification_evidence force row level security;

create policy officer_verifications_select_own
  on public.officer_verifications
  for select to authenticated
  using (auth.uid() = user_id);

create policy officer_verifications_reviewer_select_pending
  on public.officer_verifications
  for select to authenticated
  using (status = 'pending' and private.is_platform_staff('verification_reviewer'));

create policy verification_reviews_reviewer_insert
  on public.verification_reviews
  for insert to authenticated
  with check (
    reviewer_user_id = auth.uid()
    and private.is_platform_staff('verification_reviewer')
    and exists (
      select 1 from public.officer_verifications as verification
      where verification.verification_id = verification_reviews.verification_id
        and verification.status = 'pending'
        and verification.user_id <> auth.uid()
    )
  );

revoke all on public.officer_verifications, public.verification_reviews, public.verification_evidence from public, anon, authenticated;
grant select on public.officer_verifications to authenticated;
grant insert on public.verification_reviews to authenticated;

revoke all on function private.prevent_verification_history_mutation() from public, anon, authenticated;
revoke all on function private.officer_verification_is_current(uuid) from public, anon, authenticated;
revoke all on function private.transition_officer_verification(uuid, text) from public, anon, authenticated;
revoke all on function public.submit_officer_verification(text, text, text, text) from public, anon;
revoke all on function public.review_officer_verification(uuid, text, text) from public, anon;
grant execute on function public.submit_officer_verification(text, text, text, text) to authenticated;
grant execute on function public.review_officer_verification(uuid, text, text) to authenticated;
