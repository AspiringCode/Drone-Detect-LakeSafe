-- Expired real commands reduce usable capacity and must enter the same durable
-- reconciliation queue as heartbeat loss, rather than failing at queue insert.

alter table public.real_capacity_reconciliations
  drop constraint if exists real_capacity_reconciliations_trigger_check;
alter table public.real_capacity_reconciliations
  add constraint real_capacity_reconciliations_trigger_check
  check (trigger in ('heartbeat_recovery','heartbeat_expired','real_command_expired'));

create or replace function public.request_real_capacity_reconciliation(p_lake_id text,p_trigger text)
returns void language plpgsql security definer set search_path='' as $$
begin
  if p_trigger not in ('heartbeat_recovery','heartbeat_expired','real_command_expired')
     or not exists(select 1 from public.lakes where lake_id=p_lake_id) then
    raise exception 'invalid real capacity reconciliation' using errcode='23514';
  end if;
  perform private.enqueue_real_capacity_reconciliation(p_lake_id,p_trigger);
end; $$;

revoke all on function public.request_real_capacity_reconciliation(text,text) from public,anon,authenticated;
grant execute on function public.request_real_capacity_reconciliation(text,text) to service_role;
