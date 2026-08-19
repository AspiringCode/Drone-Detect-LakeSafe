-- Preserve one drone of configured inventory as the operational safety reserve.
create or replace function public.risk_plan_rebuild_context(p_lake_id text)
returns jsonb language sql security definer set search_path = '' stable as $$
  select jsonb_build_object(
    'lake_id', lake.lake_id,
    'station_id', lake.station_id,
    'shoreline_wkt', public.st_astext(lake.shoreline),
    'data_source_status', lake.data_source_status,
    'patrol_capacity', lake.drone_inventory_cap,
    'safety_reserve', 1,
    'prior_plan_id', active.zone_plan_id,
    'sources', coalesce(sources.items, '[]'::jsonb)
  )
  from public.lakes as lake
  left join lateral (
    select plan.zone_plan_id from public.zone_plans as plan
    where plan.lake_id = lake.lake_id and plan.status = 'active'
  ) as active on true
  left join lateral (
    select jsonb_agg(jsonb_build_object(
      'connector_key', connector.connector_key,
      'domain', connector.domain,
      'dataset_id', connector.dataset_id,
      'schema_version', connector.schema_version,
      'configuration', connector.configuration,
      'source_configuration', source.source_configuration
    ) order by connector.connector_key) as items
    from public.lake_data_sources as source
    join public.socrata_connectors as connector
      on connector.connector_id = source.connector_id
    where source.lake_id = lake.lake_id
      and connector.review_status = 'reviewed'
  ) as sources on true
  where lake.lake_id = p_lake_id;
$$;

revoke all on function public.risk_plan_rebuild_context(text) from public, anon, authenticated;
grant execute on function public.risk_plan_rebuild_context(text) to service_role;
