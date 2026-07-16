create table if not exists organizations (
  org_id text primary key,
  name text not null,
  station_address text not null,
  station_lat double precision not null,
  station_lon double precision not null,
  owner_user_id uuid not null references auth.users(id),
  created_at timestamptz not null default now()
);

create table if not exists lakes (
  lake_id text primary key,
  org_id text not null references organizations(org_id),
  name text not null,
  centroid_lat double precision not null,
  centroid_lon double precision not null,
  bbox jsonb,
  drone_inventory_cap integer not null default 5,
  created_at timestamptz not null default now()
);

alter table organizations enable row level security;
alter table lakes enable row level security;

create policy "Owners can view their organizations"
  on organizations for select using (auth.uid() = owner_user_id);
create policy "Owners can create their organizations"
  on organizations for insert with check (auth.uid() = owner_user_id);
create policy "Owners can update their organizations"
  on organizations for update using (auth.uid() = owner_user_id) with check (auth.uid() = owner_user_id);

create policy "Owners can view their lakes"
  on lakes for select using (exists (
    select 1 from organizations where organizations.org_id = lakes.org_id and organizations.owner_user_id = auth.uid()
 ));
create policy "Owners can create lakes for their organizations"
  on lakes for insert with check (exists (
    select 1 from organizations where organizations.org_id = lakes.org_id and organizations.owner_user_id = auth.uid()
 ));
create policy "Owners can update their lakes"
  on lakes for update using (exists (
    select 1 from organizations where organizations.org_id = lakes.org_id and organizations.owner_user_id = auth.uid()
 ));

insert into organizations (org_id, name, station_address, station_lat, station_lon, owner_user_id)
values ('org-demo', 'LakeSafe Demo Station', '400 4th Ave NE, Issaquah, WA', 47.5301, -122.0326,
        'bc14340d-ea56-4a7a-9b74-7b679f9055c4')
on conflict (org_id) do nothing;

insert into lakes (lake_id, org_id, name, centroid_lat, centroid_lon, drone_inventory_cap)
values ('lake-sammamish', 'org-demo', 'Lake Sammamish', 47.581, -122.091, 5)
on conflict (lake_id) do nothing;
