-- Additive; rollback by disabling the review UI/API before dropping this RPC and columns.
-- A review records operator acknowledgement only; it never resolves an alert or dispatches help.
alter table public.operational_alerts
  add column reviewed_at timestamptz,
  add column reviewed_by uuid references auth.users(id) on delete set null;

create function public.review_operational_alert(p_lake_id text, p_alert_id text, p_actor uuid)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare target public.operational_alerts%rowtype; was_reviewed boolean;
begin
  select * into target from public.operational_alerts
    where lake_id = p_lake_id and alert_id = p_alert_id and source = 'real' for update;
  if not found then return null; end if;
  if not exists (
    select 1 from public.station_memberships membership
    join public.station_membership_roles role on role.membership_id=membership.membership_id
    join public.officer_verifications verification on verification.user_id=membership.user_id
    where membership.station_id=target.station_id and membership.user_id=p_actor and membership.status='active'
      and role.role in ('dispatcher','station_admin') and verification.status='verified' and verification.revoked_at is null
      and (verification.expires_at is null or verification.expires_at>now())
  ) then return null; end if;
  was_reviewed := target.reviewed_at is not null;
  if not was_reviewed then
    update public.operational_alerts set reviewed_at = now(), reviewed_by = p_actor
      where alert_id = target.alert_id returning * into target;
    perform private.record_workflow_audit(p_actor, target.station_id, p_lake_id,
      'alert.review', 'allowed', 'operator reviewed alert', null,
      jsonb_build_object('alert_id', p_alert_id));
  end if;
  return jsonb_build_object('alert_id', target.alert_id, 'source', target.source,
    'reviewed', true, 'reviewed_at', target.reviewed_at, 'durable', true,
    'already_reviewed', was_reviewed);
end;
$$;
revoke all on function public.review_operational_alert(text, text, uuid) from public, anon, authenticated;
grant execute on function public.review_operational_alert(text, text, uuid) to service_role;
