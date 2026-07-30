-- Final client exposure allowlist.  Backend service-role calls remain the only
-- mutation path for workflow, fleet, alert, audit, and evidence records.

-- Force RLS on every application-owned base table.  Future migrations cannot
-- accidentally add a browser-readable table without also adding an explicit
-- policy and grant below.
do $$
declare relation record;
begin
  for relation in
    select quote_ident(namespace.nspname) || '.' || quote_ident(table_class.relname) as name
    from pg_class as table_class
    join pg_namespace as namespace on namespace.oid = table_class.relnamespace
    where namespace.nspname = 'public'
      and table_class.relkind in ('r', 'p')
      -- PostGIS and other extension relations are not LakeSafe application
      -- tables and must retain extension-managed security semantics.
      and not exists (
        select 1 from pg_depend as dependency
        where dependency.classid = 'pg_class'::regclass
          and dependency.objid = table_class.oid
          and dependency.deptype = 'e'
      )
  loop
    execute format('alter table %s enable row level security', relation.name);
    execute format('alter table %s force row level security', relation.name);
    execute format('revoke all on table %s from public, anon, authenticated', relation.name);
  end loop;
end;
$$;

-- Public projections are the only anonymous database surface.
grant select on public.public_lakes, public.public_alerts,
  public.public_patrol_presence to anon, authenticated;

-- These are the narrow authenticated reads backed by existing station/self
-- policies.  No INSERT, UPDATE, or DELETE is granted to browser roles.
grant select on public.profiles, public.stations, public.lakes,
  public.station_memberships, public.station_membership_roles,
  public.station_requests, public.station_join_requests,
  public.station_fleet_policies, public.drone_inventory,
  public.drone_availability_requests, public.zone_assignments,
  public.command_outbox, public.operational_alerts, public.audit_events
  to authenticated;
grant update (display_name) on public.profiles to authenticated;

-- Functions are backend-only by default.  The four policy helpers are the
-- sole client-role executable functions and have pinned search paths.
do $$
declare function_signature text;
begin
  for function_signature in
    select p.oid::regprocedure::text
    from pg_proc p join pg_namespace n on n.oid = p.pronamespace
    where n.nspname in ('public', 'private')
  loop
    execute format('revoke all on function %s from public, anon, authenticated', function_signature);
  end loop;
end;
$$;

grant execute on function private.jwt_aal() to authenticated;
grant execute on function private.officer_verification_is_current(uuid) to authenticated;
grant execute on function private.is_active_station_member(uuid, uuid) to authenticated;
grant execute on function private.has_station_role(uuid, text[]) to authenticated;
grant execute on function private.is_platform_staff(text) to authenticated;

-- Realtime is a separate public surface: remove every existing membership and
-- publish only delayed, sanitized projections.  Operational telemetry and
-- alert tables must never be added here.
do $$
declare publication_table record;
begin
  for publication_table in
    select schemaname, tablename
    from pg_publication_tables
    where pubname = 'supabase_realtime'
  loop
    execute format(
      'alter publication supabase_realtime drop table %I.%I',
      publication_table.schemaname, publication_table.tablename
    );
  end loop;
end;
$$;

alter publication supabase_realtime add table public.public_alerts,
  public.public_patrol_presence;
