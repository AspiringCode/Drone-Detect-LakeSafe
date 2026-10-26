-- A station toggle gates sanitized published pages and their updates. No operational data is published.
alter table public.stations add column public_pages_open boolean not null default true;
-- Preserve existing public stations, but new stations start private until explicitly opened.
alter table public.stations alter column public_pages_open set default false;
alter table public.public_lakes add column public_visible boolean not null default true;
create function private.set_public_lake_visibility() returns trigger
language plpgsql security definer set search_path='' as $$
begin
  select s.public_pages_open into new.public_visible from public.lakes l join public.stations s on s.station_id=l.station_id
    where l.lake_id=new.lake_id;
  new.public_visible:=coalesce(new.public_visible,false);
  return new;
end; $$;
create trigger public_lake_visibility before insert or update on public.public_lakes
  for each row execute function private.set_public_lake_visibility();
update public.public_lakes p set public_visible=s.public_pages_open from public.lakes l join public.stations s on s.station_id=l.station_id where p.lake_id=l.lake_id;
alter policy public_lakes_select_everyone on public.public_lakes using (public_visible);
alter policy public_alerts_select_everyone on public.public_alerts using (
  exists(select 1 from public.public_lakes p where p.lake_id=public_alerts.lake_id and p.public_visible));
alter policy public_patrol_presence_select_everyone on public.public_patrol_presence using (
  exists(select 1 from public.public_lakes p where p.lake_id=public_patrol_presence.lake_id and p.public_visible));

create function public.set_station_public_visibility(p_station_id uuid,p_actor uuid,p_visible boolean) returns jsonb
language plpgsql security definer set search_path='' as $$
declare count_lakes integer;
begin
  if p_visible is null or not exists(select 1 from public.station_memberships m
    join public.station_membership_roles r on r.membership_id=m.membership_id
    join public.officer_verifications v on v.user_id=m.user_id where m.station_id=p_station_id and m.user_id=p_actor
      and m.status='active' and r.role='station_admin' and private.officer_verification_is_current(v.verification_id)) then
    raise exception 'Verified station administrator required' using errcode='42501';
  end if;
  perform 1 from public.stations where station_id=p_station_id and status='active' for update;
  if not found then return null; end if;
  update public.stations set public_pages_open=p_visible where station_id=p_station_id;
  -- Opening explicitly publishes public lake geography, never alerts/telemetry or test fields.
  if p_visible then
    insert into public.public_lakes(lake_id,name,public_status)
      select lake_id,name,case when status='active' then 'available' else 'limited' end from public.lakes
      where station_id=p_station_id and lake_id<>'test-drone-field'
      on conflict(lake_id) do update set name=excluded.name,public_status=excluded.public_status;
  end if;
  update public.public_lakes p set public_visible=p_visible from public.lakes l
    where p.lake_id=l.lake_id and l.station_id=p_station_id;
  select count(*) into count_lakes from public.public_lakes p join public.lakes l on l.lake_id=p.lake_id where l.station_id=p_station_id;
  perform private.record_workflow_audit(p_actor,p_station_id,null,'station.public_visibility','allowed',
    case when p_visible then 'Public lake pages opened' else 'Public lake pages closed' end,null,jsonb_build_object('visible',p_visible,'published_lakes',count_lakes));
  return jsonb_build_object('visible',p_visible,'published_lakes',count_lakes);
end; $$;
revoke all on function private.set_public_lake_visibility(),public.set_station_public_visibility(uuid,uuid,boolean) from public,anon,authenticated;
grant execute on function public.set_station_public_visibility(uuid,uuid,boolean) to service_role;
