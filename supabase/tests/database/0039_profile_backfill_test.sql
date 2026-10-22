begin;
select plan(2);

select is_empty(
  $$select users.id from auth.users users left join public.profiles profiles on profiles.user_id = users.id where profiles.user_id is null$$,
  'users created before the signup trigger have profiles'
);
select is(
  (select account_class from public.profiles where user_id = 'bc14340d-ea56-4a7a-9b74-7b679f9055c4'::uuid),
  'civilian',
  'legacy organization ownership does not grant officer status'
);

select * from finish();
rollback;
