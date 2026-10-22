-- Reviewed lakes were added after the original public projection was seeded.
insert into public.public_lakes (lake_id, name, approximate_center_geohash, public_status, refreshed_at)
select lake_id, name, null, case when status = 'active' then 'available' else 'limited' end, now()
from public.lakes
on conflict (lake_id) do update set
  name = excluded.name,
  public_status = excluded.public_status,
  refreshed_at = excluded.refreshed_at;
