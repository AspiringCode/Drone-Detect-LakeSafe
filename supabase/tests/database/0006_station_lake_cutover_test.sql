begin;

select plan(12);

select has_column('public', 'stations', 'legacy_org_id', 'stations link legacy organizations');
select col_is_unique('public', 'stations', array['legacy_org_id'], 'one station maps to each legacy organization');
select has_column('public', 'lakes', 'station_id', 'lakes are station-owned');
select has_column('public', 'lakes', 'shoreline', 'lakes store shorelines');
select col_not_null('public', 'lakes', 'station_id', 'every lake has a station');
select col_not_null('public', 'lakes', 'shoreline', 'every lake has a shoreline value');
select col_has_check('public', 'lakes', 'status', 'lake status is constrained');

select is(
  (select count(*) from public.lakes where station_id is null),
  0::bigint,
  'every migrated lake maps to exactly one station'
);

select throws_ok(
  $$ update public.lakes set shoreline = st_setsrid(st_geomfromtext('MULTIPOLYGON EMPTY'), 3857) where lake_id = 'lake-sammamish' $$,
  '23514',
  null,
  'a non-4326 shoreline is rejected'
);
select throws_ok(
  $$ update public.lakes set shoreline = st_setsrid(st_geomfromtext('POLYGON EMPTY'), 4326) where lake_id = 'lake-sammamish' $$,
  '22023',
  null,
  'a valid-SRID non-multipolygon shoreline is rejected'
);

select is(
  (select status from public.stations where legacy_org_id = 'org-demo'),
  'pending',
  'a migrated legacy station remains pending'
);
select is(
  (select status from public.station_memberships as membership join public.stations as station on station.station_id = membership.station_id where station.legacy_org_id = 'org-demo' and membership.user_id = 'bc14340d-ea56-4a7a-9b74-7b679f9055c4'::uuid),
  'suspended',
  'an unverified legacy owner is suspended rather than active'
);

select * from finish();
rollback;
