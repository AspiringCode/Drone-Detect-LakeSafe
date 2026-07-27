create table public.stations (
  station_id uuid primary key default gen_random_uuid(),
  name text not null,
  status text not null default 'pending' check (status in ('pending', 'active', 'suspended')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.station_requests (
  station_request_id uuid primary key default gen_random_uuid(),
  requested_by uuid not null references auth.users(id) on delete restrict,
  requested_name text not null,
  requested_address text,
  status text not null default 'pending' check (status in ('pending', 'approved', 'rejected')),
  reviewed_by uuid references auth.users(id) on delete restrict,
  reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.station_memberships (
  membership_id uuid primary key default gen_random_uuid(),
  station_id uuid not null references public.stations(station_id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  status text not null default 'invited' check (status in ('invited', 'active', 'suspended', 'revoked')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (station_id, user_id)
);

create table public.station_membership_roles (
  membership_id uuid not null references public.station_memberships(membership_id) on delete cascade,
  role text not null check (role in ('viewer', 'dispatcher', 'safety_supervisor', 'station_admin')),
  created_at timestamptz not null default now(),
  primary key (membership_id, role)
);

create table public.station_invitations (
  invitation_id uuid primary key default gen_random_uuid(),
  station_id uuid not null references public.stations(station_id) on delete cascade,
  token_hash text not null unique,
  intended_email text not null check (intended_email = lower(btrim(intended_email))),
  expires_at timestamptz not null,
  used_at timestamptz,
  created_at timestamptz not null default now(),
  check (expires_at > created_at)
);

create table public.station_join_requests (
  station_join_request_id uuid primary key default gen_random_uuid(),
  station_id uuid not null references public.stations(station_id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  status text not null default 'pending' check (status in ('pending', 'approved', 'rejected', 'cancelled')),
  reviewed_by uuid references auth.users(id) on delete restrict,
  reviewed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index station_join_requests_one_pending_per_user_station
  on public.station_join_requests (station_id, user_id)
  where status = 'pending';

create or replace function private.prevent_station_invitation_reuse()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  if old.used_at is not null and new.used_at is distinct from old.used_at then
    raise exception 'invitation has already been used' using errcode = '23514';
  end if;

  return new;
end;
$$;

create trigger station_invitations_are_single_use
  before update on public.station_invitations
  for each row execute procedure private.prevent_station_invitation_reuse();

create or replace function private.is_active_station_member(
  target_user_id uuid,
  target_station_id uuid
)
returns boolean
language sql
security definer
set search_path = ''
as $$
  select private.jwt_aal() = 'aal2'
    and exists (
      select 1
      from public.stations as station
      join public.station_memberships as membership
        on membership.station_id = station.station_id
      join public.officer_verifications as verification
        on verification.user_id = membership.user_id
      where station.station_id = target_station_id
        and station.status = 'active'
        and membership.user_id = target_user_id
        and membership.status = 'active'
        and private.officer_verification_is_current(verification.verification_id)
    );
$$;

create or replace function private.has_station_role(
  target_station_id uuid,
  required_roles text[]
)
returns boolean
language sql
security definer
set search_path = ''
as $$
  select auth.uid() is not null
    and private.is_active_station_member(auth.uid(), target_station_id)
    and exists (
      select 1
      from public.station_memberships as membership
      join public.station_membership_roles as membership_role
        on membership_role.membership_id = membership.membership_id
      where membership.station_id = target_station_id
        and membership.user_id = auth.uid()
        and membership.status = 'active'
        and membership_role.role = any(required_roles)
    );
$$;

create or replace function private.enforce_active_station_administrator()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
  affected_station_id uuid;
begin
  if tg_table_name = 'stations' then
    select station_id into affected_station_id
    from public.stations
    where station_id = coalesce(new.station_id, old.station_id);
  elsif tg_table_name = 'station_memberships' then
    affected_station_id := coalesce(new.station_id, old.station_id);
  elsif tg_table_name = 'station_membership_roles' then
    select station_id into affected_station_id
    from public.station_memberships
    where membership_id = coalesce(new.membership_id, old.membership_id);
  elsif tg_table_name = 'officer_verifications' then
    for affected_station_id in
      select distinct station_id
      from public.station_memberships
      where user_id = coalesce(new.user_id, old.user_id)
    loop
      if exists (
        select 1 from public.stations where station_id = affected_station_id and status = 'active'
      ) and not exists (
        select 1
        from public.station_memberships as membership
        join public.station_membership_roles as membership_role
          on membership_role.membership_id = membership.membership_id
        join public.officer_verifications as verification
          on verification.user_id = membership.user_id
        where membership.station_id = affected_station_id
          and membership.status = 'active'
          and membership_role.role = 'station_admin'
          and verification.status = 'verified'
          and verification.revoked_at is null
          and (verification.expires_at is null or verification.expires_at > now())
      ) then
        raise exception 'active station % must retain an active verified station administrator', affected_station_id
          using errcode = '23514';
      end if;
    end loop;
    if tg_op = 'DELETE' then
      return old;
    end if;
    return new;
  end if;

  if affected_station_id is null then
    if tg_op = 'DELETE' then
      return old;
    end if;
    return new;
  end if;

  if exists (
    select 1
    from public.stations as station
    where station.station_id = affected_station_id
      and station.status = 'active'
  ) and not exists (
    select 1
    from public.station_memberships as membership
    join public.station_membership_roles as membership_role
      on membership_role.membership_id = membership.membership_id
    join public.officer_verifications as verification
      on verification.user_id = membership.user_id
    where membership.station_id = affected_station_id
      and membership.status = 'active'
      and membership_role.role = 'station_admin'
      and verification.status = 'verified'
      and verification.revoked_at is null
      and (verification.expires_at is null or verification.expires_at > now())
  ) then
    raise exception 'active station % must retain an active verified station administrator', affected_station_id
      using errcode = '23514';
  end if;

  if tg_op = 'DELETE' then
    return old;
  end if;
  return new;
end;
$$;

create constraint trigger stations_require_verified_administrator
  after insert or update or delete on public.stations
  deferrable initially deferred
  for each row execute procedure private.enforce_active_station_administrator();

create constraint trigger station_memberships_require_verified_administrator
  after insert or update or delete on public.station_memberships
  deferrable initially deferred
  for each row execute procedure private.enforce_active_station_administrator();

create constraint trigger station_membership_roles_require_verified_administrator
  after insert or update or delete on public.station_membership_roles
  deferrable initially deferred
  for each row execute procedure private.enforce_active_station_administrator();

create constraint trigger officer_verifications_require_verified_administrator
  after update or delete on public.officer_verifications
  deferrable initially deferred
  for each row execute procedure private.enforce_active_station_administrator();

alter table public.stations enable row level security;
alter table public.stations force row level security;
alter table public.station_requests enable row level security;
alter table public.station_requests force row level security;
alter table public.station_memberships enable row level security;
alter table public.station_memberships force row level security;
alter table public.station_membership_roles enable row level security;
alter table public.station_membership_roles force row level security;
alter table public.station_invitations enable row level security;
alter table public.station_invitations force row level security;
alter table public.station_join_requests enable row level security;
alter table public.station_join_requests force row level security;

revoke all on public.stations, public.station_requests, public.station_memberships,
  public.station_membership_roles, public.station_invitations, public.station_join_requests
  from public, anon, authenticated;

revoke all on function private.prevent_station_invitation_reuse() from public, anon, authenticated;
revoke all on function private.enforce_active_station_administrator() from public, anon, authenticated;
revoke all on function private.is_active_station_member(uuid, uuid) from public, anon;
revoke all on function private.has_station_role(uuid, text[]) from public, anon;
grant execute on function private.is_active_station_member(uuid, uuid) to authenticated;
grant execute on function private.has_station_role(uuid, text[]) to authenticated;
