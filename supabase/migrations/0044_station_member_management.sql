-- Member changes are one service-side transaction. Serialize changes within a
-- station so concurrent demotions cannot each remove its final administrator.
create or replace function public.change_station_membership(
  p_station_id uuid, p_membership_id uuid, p_actor_user_id uuid,
  p_roles text[], p_status text
) returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  member_row public.station_memberships%rowtype;
  old_roles jsonb;
  role_value text;
begin
  perform 1 from public.stations where station_id = p_station_id and status = 'active' for update;
  if not found or p_status not in ('active', 'suspended', 'revoked')
    or p_roles is null or cardinality(p_roles) = 0
    or exists (select 1 from unnest(p_roles) as role where role is null or role not in ('viewer', 'dispatcher', 'safety_supervisor', 'station_admin'))
    or not exists (
      select 1 from public.station_memberships as membership
      join public.station_membership_roles as role on role.membership_id = membership.membership_id
      join public.officer_verifications as verification on verification.user_id = membership.user_id
      where membership.station_id = p_station_id and membership.user_id = p_actor_user_id
        and membership.status = 'active' and role.role = 'station_admin'
        and verification.status = 'verified' and verification.revoked_at is null
        and (verification.expires_at is null or verification.expires_at > now())
    ) then return null; end if;
  select * into member_row from public.station_memberships
    where membership_id = p_membership_id and station_id = p_station_id for update;
  if not found then return null; end if;
  if p_status = 'active' and not exists (
    select 1 from public.officer_verifications where user_id = member_row.user_id
      and status = 'verified' and revoked_at is null and (expires_at is null or expires_at > now())
  ) then return null; end if;
  select coalesce(jsonb_agg(role order by role), '[]'::jsonb) into old_roles
    from public.station_membership_roles where membership_id = p_membership_id;
  update public.station_memberships set status = p_status, updated_at = now() where membership_id = p_membership_id;
  delete from public.station_membership_roles where membership_id = p_membership_id;
  foreach role_value in array p_roles loop
    insert into public.station_membership_roles(membership_id, role) values(p_membership_id, role_value) on conflict do nothing;
  end loop;
  perform private.assert_station_has_verified_administrator(p_station_id);
  perform private.record_workflow_audit(p_actor_user_id, p_station_id, null,
    'station.member.change', 'allowed', 'station membership access changed',
    jsonb_build_object('membership_id', p_membership_id, 'status', member_row.status, 'roles', old_roles),
    jsonb_build_object('membership_id', p_membership_id, 'status', p_status, 'roles', to_jsonb(p_roles)));
  return jsonb_build_object('membership_id', p_membership_id, 'status', p_status, 'roles', to_jsonb(p_roles));
end;
$$;
revoke all on function public.change_station_membership(uuid,uuid,uuid,text[],text) from public, anon, authenticated;
grant execute on function public.change_station_membership(uuid,uuid,uuid,text[],text) to service_role;
