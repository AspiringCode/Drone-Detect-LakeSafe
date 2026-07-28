-- Lock the active lease inside every publication transaction.
create function private.lock_risk_refresh_claim(p_lake_id text, p_claim_token uuid)
returns void language plpgsql security definer set search_path = '' as $$
begin
  perform 1 from public.risk_refresh_jobs where lake_id = p_lake_id and status = 'processing' and claim_token = p_claim_token for update;
  if found then return; end if;
  perform 1 from public.risk_source_refresh_state as state join public.lake_data_sources as source using (lake_data_source_id)
    where source.lake_id = p_lake_id and state.claim_token = p_claim_token for update of state;
  if not found then raise exception 'risk refresh claim is no longer current' using errcode = 'P0001'; end if;
end;
$$;

create function public.persist_risk_snapshot_claimed(
  p_lake_id text, p_station_id uuid, p_status text, p_source_fresh_through timestamptz, p_source_metadata jsonb,
  p_canonical_payload text, p_payload_sha256 text, p_failure_reason text, p_claim_token uuid
) returns uuid language plpgsql security definer set search_path = '' as $$
begin
  perform private.lock_risk_refresh_claim(p_lake_id, p_claim_token);
  return public.persist_risk_snapshot(p_lake_id,p_station_id,p_status,p_source_fresh_through,p_source_metadata,p_canonical_payload,p_payload_sha256,p_failure_reason);
end;
$$;

create function public.persist_validated_zone_plan_claimed(
  p_plan_id uuid,p_lake_id text,p_station_id uuid,p_snapshot_id uuid,p_prior_plan_id uuid,p_algorithm_version text,p_validation_payload jsonb,p_cells jsonb,p_claim_token uuid
) returns uuid language plpgsql security definer set search_path = '' as $$
begin
  perform private.lock_risk_refresh_claim(p_lake_id,p_claim_token);
  return public.persist_validated_zone_plan(p_plan_id,p_lake_id,p_station_id,p_snapshot_id,p_prior_plan_id,p_algorithm_version,p_validation_payload,p_cells);
end;
$$;

create function public.activate_zone_plan_claimed(p_lake_id text,p_candidate_id uuid,p_expected_prior_id uuid,p_claim_token uuid)
returns boolean language plpgsql security definer set search_path = '' as $$
begin
  perform private.lock_risk_refresh_claim(p_lake_id,p_claim_token);
  return public.activate_zone_plan(p_lake_id,p_candidate_id,p_expected_prior_id);
end;
$$;

revoke all on function public.persist_risk_snapshot_claimed(text,uuid,text,timestamptz,jsonb,text,text,text,uuid),
  public.persist_validated_zone_plan_claimed(uuid,text,uuid,uuid,uuid,text,jsonb,jsonb,uuid),
  public.activate_zone_plan_claimed(text,uuid,uuid,uuid) from public, anon, authenticated;
grant execute on function public.persist_risk_snapshot_claimed(text,uuid,text,timestamptz,jsonb,text,text,text,uuid),
  public.persist_validated_zone_plan_claimed(uuid,text,uuid,uuid,uuid,text,jsonb,jsonb,uuid),
  public.activate_zone_plan_claimed(text,uuid,uuid,uuid) to service_role;
