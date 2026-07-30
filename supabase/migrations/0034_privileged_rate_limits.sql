-- Durable, backend-only rate-limit buckets.  Every claim is serialized by the
-- composite primary key, so horizontally scaled API workers share the limit.
create table public.privileged_rate_limit_buckets (
  scope text not null check (length(scope) between 1 and 200),
  subject text not null check (length(subject) between 1 and 500),
  window_started_at timestamptz not null,
  request_count integer not null check (request_count >= 0),
  updated_at timestamptz not null default now(),
  primary key (scope, subject)
);

alter table public.privileged_rate_limit_buckets enable row level security;
alter table public.privileged_rate_limit_buckets force row level security;
revoke all on public.privileged_rate_limit_buckets from public, anon, authenticated;

create or replace function public.claim_rate_limit(
  p_scope text, p_subject text, p_limit integer, p_window_seconds integer
) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare
  bucket public.privileged_rate_limit_buckets%rowtype;
  now_at timestamptz := clock_timestamp();
  remaining integer;
begin
  if length(btrim(coalesce(p_scope, ''))) = 0
     or length(btrim(coalesce(p_subject, ''))) = 0
     or p_limit < 1 or p_limit > 10000
     or p_window_seconds < 1 or p_window_seconds > 86400 then
    raise exception 'invalid rate-limit claim' using errcode = '22023';
  end if;

  select * into bucket from public.privileged_rate_limit_buckets
    where scope = p_scope and subject = p_subject for update;
  if not found then
    insert into public.privileged_rate_limit_buckets(scope, subject, window_started_at, request_count)
      values (p_scope, p_subject, now_at, 1);
    return jsonb_build_object('allowed', true, 'retry_after_seconds', 0);
  end if;

  if bucket.window_started_at + make_interval(secs => p_window_seconds) <= now_at then
    update public.privileged_rate_limit_buckets
      set window_started_at = now_at, request_count = 1, updated_at = now_at
      where scope = p_scope and subject = p_subject;
    return jsonb_build_object('allowed', true, 'retry_after_seconds', 0);
  end if;

  if bucket.request_count < p_limit then
    update public.privileged_rate_limit_buckets
      set request_count = request_count + 1, updated_at = now_at
      where scope = p_scope and subject = p_subject;
    return jsonb_build_object('allowed', true, 'retry_after_seconds', 0);
  end if;

  remaining := greatest(1, ceil(extract(epoch from (bucket.window_started_at + make_interval(secs => p_window_seconds) - now_at)))::integer);
  return jsonb_build_object('allowed', false, 'retry_after_seconds', remaining);
end;
$$;

revoke all on function public.claim_rate_limit(text,text,integer,integer) from public, anon, authenticated;
grant execute on function public.claim_rate_limit(text,text,integer,integer) to service_role;
