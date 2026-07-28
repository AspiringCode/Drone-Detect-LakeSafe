-- Publishing a snapshot/candidate is also lease-owned, not merely queue completion.
create function public.risk_refresh_claim_is_current(p_lake_id text, p_claim_token uuid)
returns boolean language sql security definer set search_path = '' stable as $$
  select exists (
    select 1 from public.risk_refresh_jobs
    where lake_id = p_lake_id and status = 'processing' and claim_token = p_claim_token
  ) or exists (
    select 1 from public.risk_source_refresh_state as state
    join public.lake_data_sources as source using (lake_data_source_id)
    where source.lake_id = p_lake_id and state.claim_token = p_claim_token
  );
$$;
revoke all on function public.risk_refresh_claim_is_current(text, uuid) from public, anon, authenticated;
grant execute on function public.risk_refresh_claim_is_current(text, uuid) to service_role;
