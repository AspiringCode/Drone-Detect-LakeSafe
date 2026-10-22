-- Durable, service-role-only encrypted OIDC callback material.  Hashes remain
-- the database lookup/integrity values; this opaque ciphertext lets a callback
-- complete safely after a worker restart or on another application instance.
alter table public.verification_sessions
  add column encrypted_secrets text not null default '';

alter table public.verification_sessions
  alter column encrypted_secrets drop default;

create or replace function public.consume_verification_session(p_state_hash text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare session_row public.verification_sessions%rowtype;
begin
  select * into session_row from public.verification_sessions
    where state_hash = p_state_hash for update;
  if not found or session_row.status <> 'pending' then return null; end if;
  if session_row.expires_at <= now() then
    update public.verification_sessions set status = 'expired'
      where verification_session_id = session_row.verification_session_id;
    return null;
  end if;
  update public.verification_sessions set status = 'consumed', consumed_at = now()
    where verification_session_id = session_row.verification_session_id;
  perform private.record_workflow_audit(session_row.user_id, null, null,
    'verification_session.consume', 'allowed', 'state consumed',
    jsonb_build_object('status', 'pending'), jsonb_build_object('status', 'consumed'));
  return jsonb_build_object(
    'verification_session_id', session_row.verification_session_id,
    'state_hash', session_row.state_hash, 'nonce_hash', session_row.nonce_hash,
    'verifier_hash', session_row.verifier_hash, 'encrypted_secrets', session_row.encrypted_secrets,
    'user_id', session_row.user_id, 'status', 'consumed', 'expires_at', session_row.expires_at);
end;
$$;

create or replace function public.upsert_idme_verification(
  p_user_id uuid, p_provider_subject text, p_legal_name text, p_agency_name text,
  p_verified_at timestamptz, p_expires_at timestamptz
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare target_id uuid; existing_status text;
begin
  select verification_id, status into target_id, existing_status
    from public.officer_verifications where user_id = p_user_id for update;
  if not found then
    insert into public.officer_verifications (
      user_id, provider, provider_subject, method, affiliation, status,
      legal_name, agency_name, verified_at, expires_at, version, updated_at
    ) values (
      p_user_id, 'id_me', p_provider_subject, 'oidc', 'us_law_enforcement', 'pending',
      p_legal_name, p_agency_name, p_verified_at, p_expires_at, 0, now()
    ) returning verification_id, status into target_id, existing_status;
  else
    update public.officer_verifications set
      provider = 'id_me', provider_subject = p_provider_subject, method = 'oidc',
      affiliation = 'us_law_enforcement', legal_name = p_legal_name,
      agency_name = p_agency_name, verified_at = p_verified_at,
      expires_at = p_expires_at, updated_at = now()
      where verification_id = target_id;
  end if;
  if existing_status in ('not_started', 'rejected', 'expired') then
    perform private.transition_officer_verification(target_id, 'pending');
    existing_status = 'pending';
  end if;
  if existing_status = 'pending' then
    perform private.transition_officer_verification(target_id, 'verified');
  elsif existing_status <> 'verified' then
    raise exception 'verification cannot be promoted from %', existing_status using errcode = '22023';
  end if;
  perform private.record_workflow_audit(p_user_id, null, null,
    'verification.idme.upsert', 'allowed', 'provider identity verified', null,
    jsonb_build_object('verification_id', target_id, 'status', 'verified'));
  return jsonb_build_object('verification_id', target_id, 'status', 'verified');
end;
$$;

revoke all on function public.consume_verification_session(text),
  public.upsert_idme_verification(uuid, text, text, text, timestamptz, timestamptz)
  from public, anon, authenticated;
grant execute on function public.consume_verification_session(text),
  public.upsert_idme_verification(uuid, text, text, text, timestamptz, timestamptz)
  to service_role;
