create extension if not exists postgis;

alter table public.stations
  add column legacy_org_id text references public.organizations(org_id) on delete restrict,
  add constraint stations_legacy_org_id_key unique (legacy_org_id);

alter table public.lakes
  add column station_id uuid references public.stations(station_id) on delete restrict,
  add column shoreline geometry(MultiPolygon, 4326),
  add column status text not null default 'draft' check (status in ('draft', 'active', 'activity_data_unavailable', 'suspended')),
  add column created_by uuid references auth.users(id) on delete restrict,
  add column updated_at timestamptz not null default now();

-- Keep every legacy organization, but do not grant it station authority.  A
-- pending station is created for each organization and is linked exactly once.
insert into public.stations (name, status, legacy_org_id, created_at, updated_at)
select organization.name, 'pending', organization.org_id, organization.created_at, now()
from public.organizations as organization
on conflict (legacy_org_id) do nothing;

-- Existing schema has centroids and an optional JSON bounding box, but no
-- authoritative shoreline.  Store a typed empty multipolygon rather than
-- fabricating a boundary; the lake remains activity_data_unavailable until an
-- authoritative shoreline is supplied.
update public.lakes as lake
set station_id = station.station_id,
    shoreline = st_multi(st_geomfromtext('MULTIPOLYGON EMPTY', 4326)),
    status = 'activity_data_unavailable',
    created_by = organization.owner_user_id,
    updated_at = now()
from public.organizations as organization
join public.stations as station on station.legacy_org_id = organization.org_id
where lake.org_id = organization.org_id
  and lake.station_id is null;

alter table public.lakes
  alter column station_id set not null,
  alter column shoreline set not null,
  alter column created_by set not null;

alter table public.lakes
  add constraint lakes_shoreline_srid_4326
  check (st_srid(shoreline) = 4326),
  add constraint lakes_shoreline_multipolygon
  check (geometrytype(shoreline) = 'MULTIPOLYGON');

-- A migrated legacy owner must pass the same verification gate as every other
-- station user.  Suspended memberships retain migration history without
-- granting station access or activating the station.
insert into public.station_memberships (station_id, user_id, status)
select station.station_id, organization.owner_user_id, 'suspended'
from public.organizations as organization
join public.stations as station on station.legacy_org_id = organization.org_id
on conflict (station_id, user_id) do nothing;

insert into public.station_membership_roles (membership_id, role)
select membership.membership_id, 'station_admin'
from public.organizations as organization
join public.stations as station on station.legacy_org_id = organization.org_id
join public.station_memberships as membership
  on membership.station_id = station.station_id
 and membership.user_id = organization.owner_user_id
on conflict (membership_id, role) do nothing;

-- Only a still-currently-verified legacy owner is activated.  This is done
-- before station activation so the deferred administrator invariant holds.
update public.station_memberships as membership
set status = 'active', updated_at = now()
from public.stations as station,
     public.officer_verifications as verification
where membership.station_id = station.station_id
  and verification.user_id = membership.user_id
  and station.legacy_org_id is not null
  and membership.status = 'suspended'
  and verification.status = 'verified'
  and verification.revoked_at is null
  and (verification.expires_at is null or verification.expires_at > now());

update public.stations as station
set status = 'active', updated_at = now()
where station.legacy_org_id is not null
  and exists (
    select 1
    from public.station_memberships as membership
    join public.station_membership_roles as membership_role
      on membership_role.membership_id = membership.membership_id
    join public.officer_verifications as verification
      on verification.user_id = membership.user_id
    where membership.station_id = station.station_id
      and membership.status = 'active'
      and membership_role.role = 'station_admin'
      and verification.status = 'verified'
      and verification.revoked_at is null
      and (verification.expires_at is null or verification.expires_at > now())
  );

-- Legacy organization data remains available to service-side migration and
-- administration code only; authorization is now station membership based.
revoke all on public.organizations from public, anon, authenticated;
