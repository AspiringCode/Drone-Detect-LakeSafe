begin;
select plan(6);

select is_empty(
  $$select lake_id from public.public_lakes where approximate_center_geohash is null or approximate_center_geohash !~ '^[0123456789bcdefghjkmnpqrstuvwxyz]{5}$'$$,
  'published lake locations are present and coarse'
);
select is_empty(
  $$select projection.lake_id from public.public_lakes projection join public.lakes lake using (lake_id)
    where projection.approximate_center_geohash <> public.st_geohash(public.st_setsrid(public.st_makepoint(lake.centroid_lon, lake.centroid_lat), 4326), 5)$$,
  'published locations derive from lake centers'
);
select has_trigger('public', 'public_lakes', 'public_lake_location_on_publish', 'new publication derives its coarse center');
select has_trigger('public', 'lakes', 'public_lake_location_on_move', 'published location follows lake-center corrections');

update public.public_lakes set approximate_center_geohash = 'zzzzzzzzzzzz' where lake_id = 'lake-sammamish';
select is_empty(
  $$select lake_id from public.public_lakes where length(approximate_center_geohash) <> 5$$,
  'even privileged projection updates retain a coarse derived location'
);

update public.lakes set centroid_lon = centroid_lon + 0.1 where lake_id = 'lake-sammamish';
select is_empty(
  $$select projection.lake_id from public.public_lakes projection join public.lakes lake using (lake_id)
    where projection.approximate_center_geohash <> public.st_geohash(public.st_setsrid(public.st_makepoint(lake.centroid_lon, lake.centroid_lat), 4326), 5)$$,
  'location correction refreshes the projection in the same transaction'
);

select * from finish();
rollback;
