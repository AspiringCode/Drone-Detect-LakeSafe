-- Phase 2 workflows are written only by the backend service repository.  RLS
-- remains a defence-in-depth boundary for any accidentally exposed client.

alter table public.officer_verifications
  add column if not exists legal_name text,
  add column if not exists agency_name text;

create table public.verification_sessions (
  verification_session_id uuid primary key default gen_random_uuid(),
  state_hash text not null unique,
  nonce_hash text not null,
  verifier_hash text not null,
  user_id uuid not null references auth.users(id) on delete cascade,
  status text not null default 'pending'
    check (status in ('pending', 'consumed', 'expired', 'failed')),
  expires_at timestamptz not null,
  consumed_at timestamptz,
  created_at timestamptz not null default now(),
  check (expires_at > created_at)
  ,check (state_hash ~ '^[0-9a-f]{64}$')
  ,check (nonce_hash ~ '^[0-9a-f]{64}$')
  ,check (verifier_hash ~ '^[0-9a-f]{64}$')
);

alter table public.station_invitations
  add constraint station_invitations_token_hash_sha256
  check (token_hash ~ '^[0-9a-f]{64}$');

create table public.station_request_reviews (
  station_request_review_id uuid primary key default gen_random_uuid(),
  station_request_id uuid not null references public.station_requests(station_request_id) on delete cascade,
  reviewer_user_id uuid not null references auth.users(id) on delete restrict,
  decision text not null check (decision in ('approved', 'rejected')),
  note text,
  created_at timestamptz not null default now(),
  unique (station_request_id)
);

create table public.audit_events (
  audit_event_id uuid primary key default gen_random_uuid(),
  actor_user_id uuid references auth.users(id),
  actor_device_id uuid,
  session_reference text,
  station_id uuid references public.stations(station_id),
  lake_id text references public.lakes(lake_id),
  request_id uuid not null,
  action text not null,
  decision text not null check (decision in ('allowed', 'denied', 'failed')),
  reason text not null,
  prior_state jsonb,
  resulting_state jsonb,
  source_context jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  check ((actor_user_id is null) <> (actor_device_id is null))
);

create unique index if not exists station_requests_one_pending_per_user
  on public.station_requests (requested_by) where status = 'pending';
create unique index if not exists station_join_requests_one_pending_per_user_station_v2
  on public.station_join_requests (station_id, user_id) where status = 'pending';
create unique index if not exists station_invitations_one_pending_email_per_station
  on public.station_invitations (station_id, lower(intended_email))
  where used_at is null;

create or replace function private.prevent_workflow_history_mutation()
returns trigger language plpgsql set search_path = '' as $$
begin
  raise exception '% is append-only', tg_table_name using errcode = '55000';
end;
$$;

create trigger station_request_reviews_append_only
  before update or delete on public.station_request_reviews
  for each row execute procedure private.prevent_workflow_history_mutation();
create trigger audit_events_append_only
  before update or delete on public.audit_events
  for each row execute procedure private.prevent_workflow_history_mutation();

create or replace function private.record_workflow_audit(
  p_actor_user_id uuid, p_station_id uuid, p_lake_id text,
  p_action text, p_decision text, p_reason text,
  p_prior_state jsonb default null, p_resulting_state jsonb default null
) returns void language sql security definer set search_path = '' as $$
  insert into public.audit_events (
    actor_user_id, station_id, lake_id, request_id, action, decision, reason,
    prior_state, resulting_state, source_context
  ) values (
    p_actor_user_id, p_station_id, p_lake_id, gen_random_uuid(), p_action,
    p_decision, p_reason, p_prior_state, p_resulting_state,
    jsonb_build_object('component', 'workflow_repository')
  );
$$;

create or replace function public.consume_verification_session(p_state_hash text)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare session_row public.verification_sessions%rowtype;
begin
  select * into session_row from public.verification_sessions
    where state_hash = p_state_hash for update;
  if not found or session_row.status <> 'pending' then
    return null;
  end if;
  if session_row.expires_at <= now() then
    update public.verification_sessions set status = 'expired' where verification_session_id = session_row.verification_session_id;
    return null;
  end if;
  update public.verification_sessions
    set status = 'consumed', consumed_at = now()
    where verification_session_id = session_row.verification_session_id;
  perform private.record_workflow_audit(session_row.user_id, null, null,
    'verification_session.consume', 'allowed', 'state consumed',
    jsonb_build_object('status', 'pending'), jsonb_build_object('status', 'consumed'));
  return jsonb_build_object(
    'verification_session_id', session_row.verification_session_id,
    'state_hash', session_row.state_hash, 'nonce_hash', session_row.nonce_hash,
    'verifier_hash', session_row.verifier_hash, 'user_id', session_row.user_id,
    'status', 'consumed', 'expires_at', session_row.expires_at
  );
end;
$$;

create or replace function public.upsert_idme_verification(
  p_user_id uuid, p_provider_subject text, p_legal_name text, p_agency_name text,
  p_verified_at timestamptz, p_expires_at timestamptz
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare target_id uuid;
begin
  insert into public.officer_verifications (
    user_id, provider, provider_subject, method, affiliation, status,
    legal_name, agency_name, verified_at, expires_at, version, updated_at
  ) values (
    p_user_id, 'id_me', p_provider_subject, 'oidc', 'us_law_enforcement', 'pending',
    p_legal_name, p_agency_name, p_verified_at, p_expires_at, 0, now()
  ) on conflict (user_id) do update set
    provider = excluded.provider, provider_subject = excluded.provider_subject,
    method = excluded.method, affiliation = excluded.affiliation,
    legal_name = excluded.legal_name, agency_name = excluded.agency_name,
    verified_at = excluded.verified_at, expires_at = excluded.expires_at,
    updated_at = now()
  returning verification_id into target_id;
  perform private.record_workflow_audit(p_user_id, null, null,
    'verification.idme.upsert', 'allowed', 'provider identity recorded', null,
    jsonb_build_object('verification_id', target_id));
  return jsonb_build_object('verification_id', target_id);
end;
$$;

create or replace function public.create_station_request(
  p_requested_by uuid, p_requested_name text, p_requested_address text default null
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare request_row public.station_requests%rowtype;
begin
  if not exists (
    select 1 from public.officer_verifications as verification
    where verification.user_id = p_requested_by
      and private.officer_verification_is_current(verification.verification_id)
  ) then
    return null;
  end if;
  insert into public.station_requests (requested_by, requested_name, requested_address)
  values (p_requested_by, p_requested_name, p_requested_address)
  returning * into request_row;
  perform private.record_workflow_audit(p_requested_by, null, null,
    'station_request.create', 'allowed', 'pending station request created', null,
    jsonb_build_object('station_request_id', request_row.station_request_id));
  return jsonb_build_object('station_request_id', request_row.station_request_id,
    'requested_by', request_row.requested_by, 'requested_name', request_row.requested_name,
    'requested_address', request_row.requested_address, 'status', request_row.status);
exception when unique_violation then
  return null;
end;
$$;

create or replace function public.create_station_join_request(p_station_id uuid, p_user_id uuid)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare request_id uuid;
begin
  if not exists (
    select 1 from public.officer_verifications as verification
    where verification.user_id = p_user_id
      and private.officer_verification_is_current(verification.verification_id)
  ) or not exists (select 1 from public.stations where station_id = p_station_id and status = 'active') then
    return null;
  end if;
  insert into public.station_join_requests (station_id, user_id)
  values (p_station_id, p_user_id) returning station_join_request_id into request_id;
  perform private.record_workflow_audit(p_user_id, p_station_id, null,
    'station_join_request.create', 'allowed', 'pending join request created', null,
    jsonb_build_object('station_join_request_id', request_id));
  return jsonb_build_object('station_request_id', request_id, 'requested_by', p_user_id,
    'requested_name', '', 'requested_address', null, 'status', 'pending');
exception when unique_violation then
  return null;
end;
$$;

create or replace function public.create_station_invitation(
  p_station_id uuid, p_actor_user_id uuid, p_token_hash text, p_intended_email text, p_expires_at timestamptz
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare invitation_id uuid;
begin
  if not exists (
    select 1
    from public.stations as station
    join public.station_memberships as membership on membership.station_id = station.station_id
    join public.station_membership_roles as membership_role on membership_role.membership_id = membership.membership_id
    join public.officer_verifications as verification on verification.user_id = membership.user_id
    where station.station_id = p_station_id and station.status = 'active'
      and membership.user_id = p_actor_user_id and membership.status = 'active' and membership_role.role = 'station_admin'
      and private.officer_verification_is_current(verification.verification_id)
  ) then return null; end if;
  insert into public.station_invitations (station_id, token_hash, intended_email, expires_at)
  values (p_station_id, p_token_hash, lower(btrim(p_intended_email)), p_expires_at)
  returning station_invitations.invitation_id into invitation_id;
  perform private.record_workflow_audit(p_actor_user_id, p_station_id, null,
    'station_invitation.create', 'allowed', 'hash-only invitation created', null,
    jsonb_build_object('invitation_id', invitation_id));
  return jsonb_build_object('invitation_id', invitation_id);
exception when unique_violation then
  return null;
end;
$$;

create or replace function public.accept_station_invitation(
  p_token_hash text, p_user_id uuid, p_email text
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare invitation_row public.station_invitations%rowtype;
declare membership_row public.station_memberships%rowtype;
begin
  select * into invitation_row from public.station_invitations
    where token_hash = p_token_hash for update;
  if not found or invitation_row.used_at is not null
    or invitation_row.expires_at <= now()
    or invitation_row.intended_email <> lower(btrim(p_email)) then
    return null;
  end if;
  if not exists (
    select 1 from public.officer_verifications as verification
    where verification.user_id = p_user_id
      and private.officer_verification_is_current(verification.verification_id)
  ) then return null; end if;
  update public.station_invitations set used_at = now()
    where invitation_id = invitation_row.invitation_id;
  insert into public.station_memberships (station_id, user_id, status)
  values (invitation_row.station_id, p_user_id, 'active')
  on conflict (station_id, user_id) do update set status = 'active', updated_at = now()
  returning * into membership_row;
  insert into public.station_membership_roles (membership_id, role)
  values (membership_row.membership_id, 'viewer') on conflict do nothing;
  perform private.record_workflow_audit(p_user_id, invitation_row.station_id, null,
    'station_invitation.accept', 'allowed', 'invitation consumed',
    jsonb_build_object('invitation_id', invitation_row.invitation_id),
    jsonb_build_object('membership_id', membership_row.membership_id));
  return jsonb_build_object('membership_id', membership_row.membership_id,
    'station_id', membership_row.station_id, 'user_id', membership_row.user_id,
    'status', membership_row.status, 'roles', jsonb_build_array('viewer'));
end;
$$;

create or replace function public.review_station_request(
  p_station_request_id uuid, p_reviewer_user_id uuid, p_decision text, p_note text default null
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare request_row public.station_requests%rowtype;
declare station_id_value uuid; declare membership_row public.station_memberships%rowtype;
begin
  select * into request_row from public.station_requests where station_request_id = p_station_request_id for update;
  if not found or request_row.status <> 'pending' or p_decision not in ('approved', 'rejected')
    or not exists (select 1 from public.platform_staff_roles where user_id = p_reviewer_user_id and role = 'system_admin' and active)
    or not exists (select 1 from public.officer_verifications as verification where verification.user_id = request_row.requested_by and private.officer_verification_is_current(verification.verification_id))
  then return null; end if;
  update public.station_requests set status = p_decision, reviewed_by = p_reviewer_user_id,
    reviewed_at = now(), updated_at = now() where station_request_id = p_station_request_id;
  insert into public.station_request_reviews (station_request_id, reviewer_user_id, decision, note)
  values (p_station_request_id, p_reviewer_user_id, p_decision, p_note);
  if p_decision = 'rejected' then
    perform private.record_workflow_audit(p_reviewer_user_id, null, null,
      'station_request.review', 'allowed', 'request rejected',
      jsonb_build_object('status', 'pending'), jsonb_build_object('status', 'rejected'));
    return '{}'::jsonb;
  end if;
  insert into public.stations (name, status) values (request_row.requested_name, 'active') returning station_id into station_id_value;
  insert into public.station_memberships (station_id, user_id, status)
  values (station_id_value, request_row.requested_by, 'active') returning * into membership_row;
  insert into public.station_membership_roles (membership_id, role) values (membership_row.membership_id, 'station_admin');
  perform private.record_workflow_audit(p_reviewer_user_id, station_id_value, null,
    'station_request.review', 'allowed', 'request approved and administrator assigned',
    jsonb_build_object('status', 'pending'), jsonb_build_object('status', 'approved', 'membership_id', membership_row.membership_id));
  return jsonb_build_object('membership_id', membership_row.membership_id,
    'station_id', membership_row.station_id, 'user_id', membership_row.user_id,
    'status', membership_row.status, 'roles', jsonb_build_array('station_admin'));
end;
$$;

create or replace function public.review_station_join_request(
  p_station_join_request_id uuid, p_reviewer_user_id uuid, p_decision text, p_roles text[] default array['viewer']::text[]
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare request_row public.station_join_requests%rowtype; declare membership_row public.station_memberships%rowtype; role_value text;
begin
  select * into request_row from public.station_join_requests where station_join_request_id = p_station_join_request_id for update;
  if not found or request_row.status <> 'pending' or p_decision not in ('approved', 'rejected')
    or not exists (
      select 1 from public.station_memberships as membership
      join public.station_membership_roles as membership_role on membership_role.membership_id = membership.membership_id
      join public.officer_verifications as verification on verification.user_id = membership.user_id
      where membership.station_id = request_row.station_id and membership.user_id = p_reviewer_user_id
        and membership.status = 'active' and membership_role.role = 'station_admin'
        and private.officer_verification_is_current(verification.verification_id)
    )
    or not exists (select 1 from public.officer_verifications as verification where verification.user_id = request_row.user_id and private.officer_verification_is_current(verification.verification_id))
  then return null; end if;
  update public.station_join_requests set status = p_decision, reviewed_by = p_reviewer_user_id, reviewed_at = now(), updated_at = now()
    where station_join_request_id = p_station_join_request_id;
  if p_decision = 'rejected' then
    perform private.record_workflow_audit(p_reviewer_user_id, request_row.station_id, null,
      'station_join_request.review', 'allowed', 'request rejected',
      jsonb_build_object('status', 'pending'), jsonb_build_object('status', 'rejected'));
    return '{}'::jsonb;
  end if;
  insert into public.station_memberships (station_id, user_id, status) values (request_row.station_id, request_row.user_id, 'active')
    on conflict (station_id, user_id) do update set status = 'active', updated_at = now() returning * into membership_row;
  foreach role_value in array p_roles loop
    if role_value not in ('viewer', 'dispatcher', 'safety_supervisor', 'station_admin') then raise exception 'unsupported station role' using errcode = '22023'; end if;
    insert into public.station_membership_roles (membership_id, role) values (membership_row.membership_id, role_value) on conflict do nothing;
  end loop;
  perform private.record_workflow_audit(p_reviewer_user_id, request_row.station_id, null,
    'station_join_request.review', 'allowed', 'request approved',
    jsonb_build_object('status', 'pending'), jsonb_build_object('status', 'approved', 'membership_id', membership_row.membership_id));
  return jsonb_build_object('membership_id', membership_row.membership_id, 'station_id', membership_row.station_id,
    'user_id', membership_row.user_id, 'status', membership_row.status, 'roles', to_jsonb(p_roles));
end;
$$;

create or replace function public.create_station_lake(
  p_lake_id text, p_station_id uuid, p_name text, p_centroid_lat double precision,
  p_centroid_lon double precision, p_shoreline_geojson jsonb, p_created_by uuid
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare lake_row public.lakes%rowtype;
begin
  insert into public.lakes (lake_id, station_id, name, centroid_lat, centroid_lon, shoreline, created_by)
  values (p_lake_id, p_station_id, p_name, p_centroid_lat, p_centroid_lon,
    st_multi(st_setsrid(st_geomfromgeojson(p_shoreline_geojson::text), 4326)), p_created_by)
  returning * into lake_row;
  perform private.record_workflow_audit(p_created_by, p_station_id, p_lake_id,
    'lake.create', 'allowed', 'lake created', null,
    jsonb_build_object('lake_id', lake_row.lake_id));
  return jsonb_build_object('lake_id', lake_row.lake_id, 'station_id', lake_row.station_id, 'name', lake_row.name);
end;
$$;

alter table public.verification_sessions enable row level security;
alter table public.verification_sessions force row level security;
alter table public.station_request_reviews enable row level security;
alter table public.station_request_reviews force row level security;
alter table public.audit_events enable row level security;
alter table public.audit_events force row level security;

revoke all on public.verification_sessions, public.station_request_reviews, public.audit_events from public, anon, authenticated;
revoke all on function public.consume_verification_session(text), public.upsert_idme_verification(uuid, text, text, text, timestamptz, timestamptz),
  public.create_station_request(uuid, text, text), public.create_station_join_request(uuid, uuid),
  public.create_station_invitation(uuid, uuid, text, text, timestamptz), public.accept_station_invitation(text, uuid, text),
  public.review_station_request(uuid, uuid, text, text), public.review_station_join_request(uuid, uuid, text, text[]),
  public.create_station_lake(text, uuid, text, double precision, double precision, jsonb, uuid)
  from public, anon, authenticated;
grant execute on function public.consume_verification_session(text), public.upsert_idme_verification(uuid, text, text, text, timestamptz, timestamptz),
  public.create_station_request(uuid, text, text), public.create_station_join_request(uuid, uuid),
  public.create_station_invitation(uuid, uuid, text, text, timestamptz), public.accept_station_invitation(text, uuid, text),
  public.review_station_request(uuid, uuid, text, text), public.review_station_join_request(uuid, uuid, text, text[]),
  public.create_station_lake(text, uuid, text, double precision, double precision, jsonb, uuid)
  to service_role;
revoke all on function private.prevent_workflow_history_mutation() from public, anon, authenticated;
revoke all on function private.record_workflow_audit(uuid, uuid, text, text, text, text, jsonb, jsonb) from public, anon, authenticated;
