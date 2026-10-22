-- Users created before the signup trigger need civilian profiles too.
insert into public.profiles (user_id, account_class, display_name)
select id, 'civilian', raw_user_meta_data ->> 'display_name'
from auth.users
on conflict (user_id) do nothing;
