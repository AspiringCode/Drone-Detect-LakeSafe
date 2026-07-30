-- Thermal clips are never directly readable by browser credentials.  The
-- backend service signs short-lived URLs only after station authorization.
update storage.buckets set public = false where id = 'thermal-clips';

revoke all on table storage.objects from public, anon, authenticated;

-- Remove any accidental bucket-scoped policies left by a local dashboard
-- setup.  Service-role signing does not use these client policies.
drop policy if exists thermal_clips_anon_select on storage.objects;
drop policy if exists thermal_clips_authenticated_select on storage.objects;
drop policy if exists thermal_clips_authenticated_insert on storage.objects;
drop policy if exists thermal_clips_authenticated_update on storage.objects;
drop policy if exists thermal_clips_authenticated_delete on storage.objects;
