create schema if not exists private;

create table public.profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  account_class text not null default 'civilian' check (account_class in ('civilian', 'officer')),
  display_name text,
  verification_version integer not null default 0 check (verification_version >= 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.platform_staff_roles (
  user_id uuid not null references auth.users(id) on delete cascade,
  role text not null check (role in ('verification_reviewer', 'system_admin')),
  active boolean not null default true,
  created_at timestamptz not null default now(),
  primary key (user_id, role)
);

create or replace function private.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (user_id, account_class, display_name)
  values (new.id, 'civilian', new.raw_user_meta_data ->> 'display_name');

  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure private.handle_new_user();

create or replace function private.jwt_aal()
returns text
language sql
stable
set search_path = ''
as $$
  select coalesce(
    current_setting('request.jwt.claims', true)::jsonb ->> 'aal',
    ''
  );
$$;

create or replace function private.is_platform_staff(required_role text)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1
    from public.platform_staff_roles as staff_role
    where staff_role.user_id = auth.uid()
      and staff_role.role = required_role
      and staff_role.active
  );
$$;

alter table public.profiles enable row level security;
alter table public.profiles force row level security;
alter table public.platform_staff_roles enable row level security;
alter table public.platform_staff_roles force row level security;

create policy profiles_select_own
  on public.profiles
  for select
  to authenticated
  using (auth.uid() = user_id);

create policy profiles_update_own_display_name
  on public.profiles
  for update
  to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

grant select on public.profiles to authenticated;
grant update (display_name) on public.profiles to authenticated;

revoke all on public.platform_staff_roles from public, anon, authenticated;
