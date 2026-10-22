begin;
select plan(2);

select is_empty(
  $$select lake.lake_id from public.lakes lake left join public.public_lakes projection using (lake_id) where projection.lake_id is null or projection.name <> lake.name$$,
  'all configured lakes have a current public catalog entry'
);
select is_empty(
  $$select lake_id from public.public_lakes where public_status not in ('available', 'limited')$$,
  'catalog availability does not imply a safety all-clear'
);

select * from finish();
rollback;
