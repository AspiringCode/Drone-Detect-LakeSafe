-- One-time dev seed: registers the real-drone test square and attaches a drone to it.
-- Not a migration. Run once in the Supabase SQL editor after migrations are applied,
-- after the drone was registered via POST /api/stations/{station_id}/inventory/real.
-- Geometry matches backend/fixtures/drone_test_area.json (200 m square, Sammamish WA).
do $$
declare
  v_station_id uuid := '00000000-0000-0000-0000-000000000000';  -- your active station
  v_admin_user_id uuid := '00000000-0000-0000-0000-000000000000';  -- station admin (auth.users.id)
  v_drone_id uuid := '00000000-0000-0000-0000-000000000000';  -- inventory_id returned by registration
begin
  if not exists (select 1 from public.lakes where lake_id = 'test-drone-field') then
    perform public.create_station_lake(
      'test-drone-field', v_station_id, 'Drone Test Field (not a lake)', 47.592028, -122.032472,
      '{"type":"Polygon","coordinates":[[[-122.033804,47.591130],[-122.031140,47.591130],[-122.031140,47.592926],[-122.033804,47.592926],[-122.033804,47.591130]]]}'::jsonb,
      v_admin_user_id, 'fallback_coverage');
  end if;
  -- Heartbeats only reach the live map for drones attached to a lake; the schema
  -- ties lake_id to the 'circulating' lifecycle.
  update public.drone_inventory set lake_id = 'test-drone-field', lifecycle = 'circulating', updated_at = now()
    where inventory_id = v_drone_id and station_id = v_station_id and source = 'real';
  if not found then raise exception 'real drone % not found at station %', v_drone_id, v_station_id; end if;
end $$;
