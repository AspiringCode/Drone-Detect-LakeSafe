-- A platform reviewer must remain independent from the person requesting a station.
create or replace function public.review_station_request(
  p_station_request_id uuid, p_reviewer_user_id uuid, p_decision text, p_note text default null
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare request_row public.station_requests%rowtype;
declare station_id_value uuid; declare membership_row public.station_memberships%rowtype;
begin
  select * into request_row from public.station_requests where station_request_id = p_station_request_id for update;
  if not found or request_row.status <> 'pending' or p_decision not in ('approved', 'rejected')
    or request_row.requested_by = p_reviewer_user_id
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
